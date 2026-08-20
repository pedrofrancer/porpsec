import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.audit import Audit
from app.models.opportunity import Opportunity
from app.models.message import Message
from app.models.prospection import ProspectingQueue, OptOut, ActionLog

logger = logging.getLogger("dispatcher")

AUTO_ENQUEUE_BATCH_SIZE = 5


class ContentValidator:
    """Valida mensagem antes de enviar."""

    PLACEHOLDER_PATTERNS = [
        r"\[nome\]",
        r"\[empresa\]",
        r"\{\{.*?\}\}",
        r"\[.*?\]",
        r"TODO",
        r"PLACEHOLDER",
    ]

    MAX_LENGTH = 1000

    @staticmethod
    def validate(message: str, company_name: str) -> tuple[bool, str | None]:
        if not message or not message.strip():
            return False, "Mensagem vazia"

        if len(message) > ContentValidator.MAX_LENGTH:
            return False, f"Mensagem muito longa ({len(message)} chars, max {ContentValidator.MAX_LENGTH})"

        for pattern in ContentValidator.PLACEHOLDER_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return False, f"Placeholder detectado: {pattern}"

        if company_name.lower() not in message.lower():
            return False, f"Nome da empresa '{company_name}' nao encontrado na mensagem"

        return True, None


class WarmupManager:
    """Gerencia curva de aquecimento do numero."""

    WARMUP_FILE = Path(__file__).parent.parent.parent / "warmup_state.json"

    @classmethod
    def _load_state(cls) -> dict:
        if cls.WARMUP_FILE.exists():
            return json.loads(cls.WARMUP_FILE.read_text(encoding="utf-8"))
        return {"first_use_date": None, "total_sent": 0}

    @classmethod
    def _save_state(cls, state: dict):
        cls.WARMUP_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    @classmethod
    def get_first_use_date(cls) -> datetime | None:
        state = cls._load_state()
        if state.get("first_use_date"):
            return datetime.fromisoformat(state["first_use_date"])
        return None

    @classmethod
    def register_first_use(cls):
        state = cls._load_state()
        if not state.get("first_use_date"):
            state["first_use_date"] = datetime.now(timezone.utc).isoformat()
            cls._save_state(state)

    @classmethod
    def get_max_today(cls) -> int:
        state = cls._load_state()
        curve = settings.warmup_curve_list

        if not state.get("first_use_date"):
            return curve[0] if curve else settings.DAILY_SEND_LIMIT

        first_use = datetime.fromisoformat(state["first_use_date"])
        days_since = (datetime.now(timezone.utc) - first_use).days

        if days_since >= len(curve):
            return settings.DAILY_SEND_LIMIT

        return curve[days_since]

    @classmethod
    def get_day_number(cls) -> int:
        state = cls._load_state()
        if not state.get("first_use_date"):
            return 1
        first_use = datetime.fromisoformat(state["first_use_date"])
        return (datetime.now(timezone.utc) - first_use).days + 1


class Dispatcher:
    """Pipeline completo: coleta -> audita -> oportunidade -> mensagem -> envio."""

    def __init__(self, db: Session | None = None):
        self._db = db
        self._paused = False
        self._running = False
        self._last_error = None
        self._consecutive_errors = 0
        self._circuit_open = False
        self._loop_task: asyncio.Task | None = None
        self._started_at: datetime | None = None
        self._last_cycle_at: datetime | None = None
        self._next_cycle_at: datetime | None = None

    @property
    def db(self) -> Session:
        if self._db is None or self._db.is_active is False:
            from app.core.database import SessionLocal
            self._db = SessionLocal()
        return self._db

    def replace_db(self, db: Session):
        self._db = db

    @property
    def status(self) -> dict:
        return {
            "running": self._running,
            "paused": self._paused,
            "circuit_open": self._circuit_open,
            "last_error": self._last_error,
            "consecutive_errors": self._consecutive_errors,
            "warmup_day": WarmupManager.get_day_number(),
            "warmup_max_today": WarmupManager.get_max_today(),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "next_cycle_at": self._next_cycle_at.isoformat() if self._next_cycle_at else None,
            "loop_active": self._loop_task is not None and not self._loop_task.done(),
        }

    def pause(self):
        self._paused = True
        logger.info("Dispatcher pausado")

    def resume(self):
        self._paused = False
        self._circuit_open = False
        self._consecutive_errors = 0
        logger.info("Dispatcher retomado")

    async def run_loop(self):
        """Loop infinito de background. Chamar via asyncio.create_task()."""
        self._started_at = datetime.now(timezone.utc)
        logger.info(
            f"Dispatcher loop iniciado (intervalo={settings.DISPATCHER_INTERVAL_SECONDS}s)"
        )

        while True:
            self._next_cycle_at = datetime.now(timezone.utc) + timedelta(
                seconds=settings.DISPATCHER_INTERVAL_SECONDS
            )

            await asyncio.sleep(settings.DISPATCHER_INTERVAL_SECONDS)

            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Excecao nao tratada no loop: {e}", exc_info=True)
                self._last_error = str(e)
                self._consecutive_errors += 1
                self._check_circuit_breaker()

    def stop(self):
        """Para o loop de background."""
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            logger.info("Dispatcher loop cancelado")
        self._loop_task = None
        self._next_cycle_at = None

    def _check_circuit_breaker(self):
        if self._consecutive_errors >= 5:
            self._circuit_open = True
            self._paused = True
            logger.critical(
                "CIRCUIT BREAKER ATIVADO: 5 erros consecutivos. Envios pausados."
            )
            log_path = Path(__file__).parent.parent.parent / "dispatcher_alerts.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now(timezone.utc).isoformat()}] CIRCUIT BREAKER: 5 erros consecutivos\n")

    def _is_within_send_window(self) -> bool:
        now = datetime.now(timezone.utc)
        hour = now.hour
        return settings.SEND_WINDOW_START <= hour < settings.SEND_WINDOW_END

    def _is_weekday(self) -> bool:
        return datetime.now(timezone.utc).weekday() < 5

    def _can_send_hourly(self) -> bool:
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        count = self.db.query(func.count(Message.id)).filter(
            Message.sent_at >= hour_start,
            Message.status == "enviado",
        ).scalar()
        return count < settings.HOURLY_SEND_LIMIT

    def _can_send_daily(self) -> bool:
        max_today = WarmupManager.get_max_today()
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = self.db.query(func.count(Message.id)).filter(
            Message.sent_at >= today_start,
            Message.status == "enviado",
        ).scalar()
        return sent_today < max_today

    def _check_opt_out(self, company: Company) -> bool:
        if company.phone:
            if self.db.query(OptOut).filter(OptOut.contact_identifier == company.phone).first():
                return True
        if company.instagram:
            if self.db.query(OptOut).filter(OptOut.contact_identifier == company.instagram).first():
                return True
        return False

    def _has_active_message(self, company_id: int) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return self.db.query(Message).filter(
            Message.company_id == company_id,
            Message.status.in_(["rascunho", "aprovado", "enviado"]),
            Message.generated_at >= cutoff,
        ).first() is not None

    def _get_eligible_companies(self) -> list[Company]:
        """Busca empresas elegíveis para auto-enfileiramento."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        opted_out_phones = [
            row[0] for row in self.db.query(OptOut.contact_identifier).all()
        ]

        active_queue_company_ids = [
            row[0] for row in self.db.query(ProspectingQueue.company_id)
            .filter(ProspectingQueue.status.in_(["PENDENTE", "ERRO"]))
            .all()
        ]

        recent_msg_company_ids = [
            row[0] for row in self.db.query(Message.company_id)
            .filter(
                Message.generated_at >= cutoff,
                Message.status.in_(["rascunho", "aprovado", "enviado"]),
            )
            .distinct()
            .all()
        ]

        exclude_ids = set(active_queue_company_ids + recent_msg_company_ids)

        companies = self.db.query(Company).filter(
            Company.phone.isnot(None),
            Company.phone != "",
        ).all()

        eligible = []
        for c in companies:
            if c.id in exclude_ids:
                continue
            if c.phone in opted_out_phones:
                continue
            if c.instagram and c.instagram in opted_out_phones:
                continue
            eligible.append(c)

        return eligible[:AUTO_ENQUEUE_BATCH_SIZE]

    async def _auto_enqueue(self) -> int:
        """Auto-enfileira empresas elegíveis. Retorna quantidade processada."""
        eligible = self._get_eligible_companies()

        if not eligible:
            logger.info("Nenhuma empresa nova elegivel — base esgotada")
            return 0

        logger.info(f"Empresas elegiveis para auto-enfileiramento: {len(eligible)}")
        enqueued = 0

        for company in eligible:
            try:
                audit = self.db.query(Audit).filter(
                    Audit.company_id == company.id
                ).order_by(Audit.id.desc()).first()

                if not audit:
                    try:
                        from app.auditors.website_auditor import WebsiteAuditor
                        auditor = WebsiteAuditor(self.db)
                        result = await auditor.audit(company.id)
                        audit = auditor.save_audit(company.id, result)
                    except Exception as e:
                        logger.warning(f"Auditoria falhou para {company.name}: {e}")

                opportunities = self.db.query(Opportunity).filter(
                    Opportunity.company_id == company.id
                ).all()

                if not opportunities:
                    try:
                        from app.opportunities.engine import OpportunityEngine
                        engine = OpportunityEngine(self.db)
                        results = engine.evaluate(company)
                        engine.save_opportunities(company, results)
                        opportunities = self.db.query(Opportunity).filter(
                            Opportunity.company_id == company.id
                        ).all()
                    except Exception as e:
                        logger.warning(f"Oportunidades falharam para {company.name}: {e}")

                from app.llm.sales_agent import generate_outreach_message
                from app.api.v1.endpoints.diagnosis import build_diagnosis

                diagnosis = build_diagnosis(company, audit, opportunities, self.db)
                message_text = await generate_outreach_message(
                    company, audit, opportunities, diagnosis
                )

                valid, error = ContentValidator.validate(message_text, company.name)
                msg_status = "aprovado" if valid else "erro_validacao"

                if valid:
                    approved_at = datetime.now(timezone.utc)
                else:
                    approved_at = None
                    logger.warning(f"Validacao falhou para {company.name}: {error}")

                msg = Message(
                    company_id=company.id,
                    opportunity_ids=json.dumps([o.id for o in opportunities[:3]]),
                    message_text=message_text,
                    status=msg_status,
                    generated_at=datetime.now(timezone.utc),
                    approved_at=approved_at,
                    llm_model=settings.LLM_MODEL,
                )
                self.db.add(msg)
                self.db.commit()

                entry = ProspectingQueue(
                    company_id=company.id,
                    status="PENDENTE" if valid else "ERRO",
                    notes="Auto-enfileirado" if valid else f"Validacao falhou: {error}",
                )
                self.db.add(entry)
                self.db.commit()
                enqueued += 1

                logger.info(
                    f"Auto-enfileirado: {company.name} "
                    f"(msg={msg_status}, queue={'PENDENTE' if valid else 'ERRO'})"
                )

            except Exception as e:
                logger.error(f"Erro ao auto-enfileirar {company.name}: {e}")
                self.db.rollback()

        return enqueued

    def _get_pending_companies(self) -> list[ProspectingQueue]:
        return self.db.query(ProspectingQueue).filter(
            ProspectingQueue.status == "PENDENTE"
        ).order_by(ProspectingQueue.created_at.asc()).all()

    async def _process_company(self, entry: ProspectingQueue) -> bool:
        """Processa uma empresa do pipeline completo. Retorna True se enviou."""
        company = self.db.get(Company, entry.company_id)
        if not company:
            entry.status = "ERRO"
            entry.notes = "Empresa nao encontrada"
            self.db.commit()
            return False

        if self._check_opt_out(company):
            entry.status = "BLOQUEADO_OPT_OUT"
            self.db.commit()
            logger.info(f"Empresa {company.name} bloqueada (opt-out)")
            return False

        if self._has_active_message(company.id):
            entry.status = "JA_ENVIADO"
            self.db.commit()
            logger.info(f"Empresa {company.name} ja possui mensagem ativa")
            return False

        audit = self.db.query(Audit).filter(Audit.company_id == company.id).order_by(Audit.id.desc()).first()

        if not audit:
            try:
                from app.auditors.website_auditor import WebsiteAuditor
                auditor = WebsiteAuditor(self.db)
                result = await auditor.audit(company.id)
                audit = auditor.save_audit(company.id, result)
            except Exception as e:
                logger.warning(f"Auditoria falhou para {company.name}: {e}")

        opportunities = self.db.query(Opportunity).filter(Opportunity.company_id == company.id).all()

        if not opportunities:
            try:
                from app.opportunities.engine import OpportunityEngine
                engine = OpportunityEngine(self.db)
                results = engine.evaluate(company)
                engine.save_opportunities(company, results)
                opportunities = self.db.query(Opportunity).filter(Opportunity.company_id == company.id).all()
            except Exception as e:
                logger.warning(f"Oportunidades falharam para {company.name}: {e}")

        from app.llm.sales_agent import generate_outreach_message
        from app.api.v1.endpoints.diagnosis import build_diagnosis

        diagnosis = build_diagnosis(company, audit, opportunities, self.db)
        message_text = await generate_outreach_message(company, audit, opportunities, diagnosis)

        valid, error = ContentValidator.validate(message_text, company.name)
        if not valid:
            msg = Message(
                company_id=company.id,
                opportunity_ids=json.dumps([o.id for o in opportunities[:3]]),
                message_text=message_text,
                status="erro_validacao",
                generated_at=datetime.now(timezone.utc),
                llm_model=settings.LLM_MODEL,
            )
            self.db.add(msg)
            self.db.commit()
            logger.warning(f"Validacao falhou para {company.name}: {error}")
            return False

        msg = Message(
            company_id=company.id,
            opportunity_ids=json.dumps([o.id for o in opportunities[:3]]),
            message_text=message_text,
            status="aprovado",
            generated_at=datetime.now(timezone.utc),
            approved_at=datetime.now(timezone.utc),
            llm_model=settings.LLM_MODEL,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)

        return await self._send_message(msg, company)

    async def _send_message(self, msg: Message, company: Company) -> bool:
        """Envia mensagem via WhatsApp client."""
        from app.sending.whatsapp_client import WhatsAppClient

        client = WhatsAppClient()

        try:
            if not await client.is_connected():
                logger.warning("WhatsApp nao conectado")
                return False

            result = await client.send(company.phone, msg.message_text)

            msg.status = "enviado"
            msg.sent_at = datetime.now(timezone.utc)
            self.db.commit()

            WarmupManager.register_first_use()

            log_entry = ActionLog(
                company_id=company.id,
                contact_id=company.phone,
                action="mensagem_enviada",
                details=json.dumps({"message_id": msg.id, "result": result}),
            )
            self.db.add(log_entry)

            queue_entry = self.db.query(ProspectingQueue).filter(
                ProspectingQueue.company_id == company.id
            ).first()
            if queue_entry:
                queue_entry.status = "ENVIADO"
                queue_entry.last_followup_at = datetime.now(timezone.utc)

            self.db.commit()

            self._consecutive_errors = 0
            logger.info(f"Mensagem enviada para {company.name} ({company.phone})")
            return True

        except Exception as e:
            msg.status = "erro_envio"
            self.db.commit()

            self._consecutive_errors += 1
            self._last_error = str(e)
            self._check_circuit_breaker()

            log_entry = ActionLog(
                company_id=company.id,
                contact_id=company.phone,
                action="erro_envio",
                details=str(e),
            )
            self.db.add(log_entry)
            self.db.commit()

            logger.error(f"Erro ao enviar para {company.name}: {e}")
            return False

    async def run_cycle(self):
        """Executa um ciclo completo do dispatcher."""
        if self._paused or self._circuit_open:
            return

        if not self._is_weekday():
            logger.info("Fim de semana — skip")
            return

        if not self._is_within_send_window():
            logger.info("Fora da janela de envio — skip")
            return

        if not self._can_send_daily():
            logger.info("Limite diario atingido — skip")
            return

        if not self._can_send_hourly():
            logger.info("Limite horario atingido — skip")
            return

        self._running = True
        self._last_cycle_at = datetime.now(timezone.utc)
        logger.info("Ciclo do dispatcher iniciado")

        try:
            enqueued = await self._auto_enqueue()
            logger.info(f"Novas empresas processadas: {enqueued}")

            pending = self._get_pending_companies()
            logger.info(f"Empresas na fila: {len(pending)}")

            for entry in pending:
                if self._paused or self._circuit_open:
                    break

                if not self._can_send_daily() or not self._can_send_hourly():
                    break

                await self._process_company(entry)

                delay = random.uniform(
                    settings.SEND_DELAY_MIN_MS / 1000,
                    settings.SEND_DELAY_MAX_MS / 1000,
                )
                logger.debug(f"Delay: {delay:.1f}s")
                await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"Erro no ciclo: {e}")
        finally:
            self._running = False
            logger.info("Ciclo do dispatcher finalizado")
