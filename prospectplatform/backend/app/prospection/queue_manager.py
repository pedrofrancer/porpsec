from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.prospection import ProspectingQueue, OptOut, ActionLog
from app.models.message import Message
from app.models.company import Company
from app.core.config import settings


class QueueManager:
    """Gerencia fila de prospecção, rate limit e opt-out."""

    def __init__(self, db: Session):
        self.db = db

    def add_to_queue(self, company_id: int, notes: str | None = None) -> ProspectingQueue:
        """Adiciona empresa à fila de prospecção."""
        company = self.db.get(Company, company_id)

        if company and self.is_opted_out(phone=company.phone, instagram=company.instagram):
            existing = self.db.query(ProspectingQueue).filter(
                ProspectingQueue.company_id == company_id
            ).first()
            if existing:
                existing.status = "BLOQUEADO_OPT_OUT"
                self.db.commit()
                self.db.refresh(existing)
                return existing
            entry = ProspectingQueue(
                company_id=company_id,
                status="BLOQUEADO_OPT_OUT",
                notes="Opt-out detectado",
            )
            self.db.add(entry)
            self.db.commit()
            self.db.refresh(entry)
            return entry

        existing = self.db.query(ProspectingQueue).filter(
            ProspectingQueue.company_id == company_id
        ).first()

        if existing:
            if existing.status in ("BLOQUEADO_OPT_OUT", "ENVIADO"):
                return existing
            existing.status = "PENDENTE"
            existing.notes = notes or existing.notes
            self.db.commit()
            self.db.refresh(existing)
            return existing

        entry = ProspectingQueue(
            company_id=company_id,
            status="PENDENTE",
            notes=notes,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def is_opted_out(self, phone: str | None = None, instagram: str | None = None) -> bool:
        """Verifica se contato está em lista de opt-out."""
        if phone:
            if self.db.query(OptOut).filter(OptOut.contact_identifier == phone).first():
                return True
        if instagram:
            if self.db.query(OptOut).filter(OptOut.contact_identifier == instagram).first():
                return True
        return False

    def register_opt_out(self, identifier: str, reason: str | None = None, source: str = "manual") -> OptOut:
        """Registra opt-out permanente."""
        existing = self.db.query(OptOut).filter(OptOut.contact_identifier == identifier).first()
        if existing:
            return existing

        opt_out = OptOut(
            contact_identifier=identifier,
            reason=reason,
            source=source,
        )
        self.db.add(opt_out)

        # Bloquear empresa na fila se existir
        company = self.db.query(Company).filter(
            (Company.phone == identifier) | (Company.instagram == identifier)
        ).first()
        if company:
            queue_entry = self.db.query(ProspectingQueue).filter(
                ProspectingQueue.company_id == company.id
            ).first()
            if queue_entry:
                queue_entry.status = "BLOQUEADO_OPT_OUT"

        self.db.commit()
        return opt_out

    def can_send_today(self) -> bool:
        """Verifica se ainda é possível enviar hoje (rate limit)."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = self.db.query(func.count(Message.id)).filter(
            Message.sent_at >= today_start,
            Message.status == "enviado",
        ).scalar()
        return sent_today < settings.DAILY_SEND_LIMIT

    def get_send_count_today(self) -> int:
        """Retorna quantas mensagens foram enviadas hoje."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.db.query(func.count(Message.id)).filter(
            Message.sent_at >= today_start,
            Message.status == "enviado",
        ).scalar()

    def get_queue(self, status: str | None = None) -> list[ProspectingQueue]:
        """Retorna fila de prospecção."""
        query = self.db.query(ProspectingQueue)
        if status:
            query = query.filter(ProspectingQueue.status == status)
        return query.order_by(ProspectingQueue.created_at.desc()).all()

    def approve_message(self, message_id: int) -> Message:
        """Aprova mensagem para envio (apenas se rate limit permite)."""
        if not self.can_send_today():
            raise ValueError(f"Limite diário atingido ({settings.DAILY_SEND_LIMIT} mensagens)")

        msg = self.db.get(Message, message_id)
        if not msg:
            raise ValueError("Mensagem não encontrada")

        company = self.db.get(Company, msg.company_id)
        if company and self.is_opted_out(company.phone, company.instagram):
            raise ValueError("Empresa está em lista de opt-out")

        msg.status = "aprovado"
        msg.approved_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def mark_sent(self, message_id: int) -> Message:
        """Marca mensagem como enviada."""
        msg = self.db.get(Message, message_id)
        if not msg:
            raise ValueError("Mensagem não encontrada")

        msg.status = "enviado"
        msg.sent_at = datetime.now(timezone.utc)

        # Atualizar fila
        queue_entry = self.db.query(ProspectingQueue).filter(
            ProspectingQueue.company_id == msg.company_id
        ).first()
        if queue_entry:
            queue_entry.status = "ENVIADO"
            queue_entry.last_followup_at = datetime.now(timezone.utc)

        # Log de ação
        log = ActionLog(
            company_id=msg.company_id,
            contact_id=company.phone if (company := self.db.get(Company, msg.company_id)) else None,
            action="mensagem_enviada",
            details=f"Message ID: {message_id}",
        )
        self.db.add(log)
        self.db.commit()
        return msg
