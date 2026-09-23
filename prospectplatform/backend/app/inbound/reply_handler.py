"""Casa e-mail recebido com o outreach e decide o que fazer (resposta, descadastro, bounce)."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auditors.extractors import registrable_domain
from app.i18n import is_opt_out_reply
from app.inbound.email_parser import ParsedEmail
from app.models.company import Company
from app.models.inbound import InboundReply
from app.models.message import Message
from app.models.prospection import ActionLog, OptOut, ProspectingQueue

logger = logging.getLogger("inbound")


class ReplyEventHandler:
    def __init__(self, db: Session, on_first_reply=None):
        self.db = db
        # Chamado com (reply, company, outreach_msg) na primeira resposta real (gera a previa).
        self.on_first_reply = on_first_reply

    def _find_outreach(self, parsed: ParsedEmail) -> Message | None:
        ids = parsed.thread_ids
        if ids:
            msg = self.db.query(Message).filter(
                Message.channel == "email",
                Message.thread_id.in_(ids),
            ).order_by(Message.id.desc()).first()
            if msg:
                return msg
        if parsed.is_bounce or not parsed.from_address:
            return None
        # Sem cabecalho de thread (alguns clientes cortam): mesmo endereco ou mesmo dominio da empresa.
        domain = registrable_domain(parsed.from_address)
        candidates = self.db.query(Message).join(Company).filter(
            Message.channel == "email",
            Message.message_type == "outreach",
            Message.status == "enviado",
        ).order_by(Message.id.desc()).all()
        for msg in candidates:
            email = (msg.company.email or "").lower()
            if email == parsed.from_address or (domain and registrable_domain(email) == domain):
                return msg
        return None

    def handle(self, parsed: ParsedEmail) -> InboundReply | None:
        """Registra o e-mail se pertence a um outreach nosso. Idempotente por Message-ID."""
        external_id = parsed.message_id or f"noid:{parsed.from_address}:{parsed.received_at.isoformat()}"
        if self.db.query(InboundReply).filter(InboundReply.external_id == external_id).first():
            return None

        outreach = self._find_outreach(parsed)
        if outreach is None:
            return None
        company = outreach.company

        if parsed.is_bounce:
            kind = "bounce"
        elif is_opt_out_reply(parsed.text) or parsed.subject.strip().upper() == "STOP":
            kind = "opt_out"
        else:
            kind = "reply"

        is_first = kind == "reply" and not self.db.query(InboundReply).filter(
            InboundReply.company_id == company.id,
            InboundReply.kind == "reply",
        ).first()

        reply = InboundReply(
            company_id=company.id,
            message_id=outreach.id,
            channel="email",
            external_id=external_id,
            from_address=parsed.from_address,
            subject=parsed.subject[:300],
            raw_content=parsed.text[:20000],
            kind=kind,
            is_first_reply=is_first,
            received_at=parsed.received_at,
            processed_at=datetime.now(timezone.utc),
        )
        self.db.add(reply)

        queue = self.db.query(ProspectingQueue).filter(ProspectingQueue.company_id == company.id).first()

        if kind == "bounce":
            outreach.status = "bounce"
            outreach.last_error = "Entrega recusada pelo servidor de destino"
        elif kind == "opt_out":
            for identifier in {company.email, parsed.from_address} - {None}:
                if not self.db.query(OptOut).filter(OptOut.contact_identifier == identifier.lower()).first():
                    self.db.add(OptOut(contact_identifier=identifier.lower(), reason="Respondeu STOP",
                                       source="email_reply"))
            if queue:
                queue.status = "BLOQUEADO_OPT_OUT"
        elif queue and queue.status in ("ENVIADO", "PENDENTE"):
            queue.status = "RESPONDEU"

        self.db.add(ActionLog(
            company_id=company.id,
            contact_id=parsed.from_address,
            action=f"email_{kind}",
            details=json.dumps({"outreach_message_id": outreach.id, "subject": parsed.subject}, default=str),
        ))
        self.db.commit()
        logger.info(f"E-mail de {company.name}: {kind}{' (primeira resposta)' if is_first else ''}")

        if is_first and self.on_first_reply:
            try:
                self.on_first_reply(reply, company, outreach)
            except Exception as e:
                logger.error(f"Falha ao preparar previa para {company.name}: {e}", exc_info=True)

        return reply
