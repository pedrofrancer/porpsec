import asyncio
import json
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.audit import Audit
from app.models.opportunity import Opportunity
from app.models.message import Message
from app.models.prospection import ProspectingQueue, OptOut, ActionLog
from app.core.countries import CountrySettings, country_code_for_company, get_country
from app.prospecting.channel_router import resolve_channel

logger = logging.getLogger("dispatcher")

AUTO_ENQUEUE_BATCH_SIZE = 5
COLLECTION_COOLDOWN_DAYS = 3
BRT = ZoneInfo("America/Sao_Paulo")
# Fuso usado para contar "hoje"/"esta hora" nos limites de cada canal.
CHANNEL_TZ = {"whatsapp": BRT, "email": ZoneInfo("Europe/Brussels")}
# Status de fila que tiram a empresa do auto-enfileiramento.
_QUEUE_BLOCKING = ["PENDENTE", "ERRO", "NAO_ELEGIVEL", "BLOQUEADO_OPT_OUT"]
COLLECTION_TIMEOUT_SECONDS = 120
_TARGETS_FILE = Path(__file__).parent.parent.parent.parent / "config" / "collection_targets.yaml"


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

    SPECIFICITY_KEYWORDS = [
        r"site", r"website", r"www\.", r"\.com", r"\.com\.br",
        r"instagram", r"@[\w.]+",
        r"google", r"nota", r"avalia[cç][aã]o", r"estrela",
        r"agendamento", r"marcar", r"hor[aá]rio",
        r"whatsapp", r"zap",
        r"lento", r"velocidade", r"carregando", r"demora",
        r"celular", r"mobile", r"responsivo", r"tela",
        r"bot[aã]o", r"link", r"contato",
        r"faltando", r"ausente", r"sem\s", r"n[aã]o\s+tem",
        r"incompleto", r"perfil",
        r"foto", r"fotos", r"imagem",
        r"blog", r"post", r"conte[uú]do",
        r"HTTPS", r"SSL", r"viewport",
    ]

    @staticmethod
    def validate(
        message: str,
        company_name: str,
        audit: "Audit | None" = None,
        opportunities: list | None = None,
    ) -> tuple[bool, str | None]:
        if not message or not message.strip():
            return False, "Mensagem vazia"

        if len(message) > ContentValidator.MAX_LENGTH:
            return False, f"Mensagem muito longa ({len(message)} chars, max {ContentValidator.MAX_LENGTH})"

        for pattern in ContentValidator.PLACEHOLDER_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return False, f"Placeholder detectado: {pattern}"

        if company_name.lower() not in message.lower():
            return False, f"Nome da empresa '{company_name}' nao encontrado na mensagem"

        msg_lower = message.lower()
        has_specificity = any(
            re.search(kw, msg_lower) for kw in ContentValidator.SPECIFICITY_KEYWORDS
        )
        if not has_specificity:
            return False, "Mensagem generica — nenhum dado especifico da empresa mencionado"

        if opportunities:
            opp_keywords = []
            for opp in opportunities[:3]:
                words = opp.problem.lower().split()
                opp_keywords.extend(w for w in words if len(w) > 3)
            if opp_keywords:
                mentioned_opp = any(kw in msg_lower for kw in opp_keywords)
                if not mentioned_opp:
                    return False, "Mensagem nao referencia nenhuma oportunidade identificada"

        return True, None


class WarmupManager:
    """Curva de aquecimento por canal (numero de WhatsApp e caixa de e-mail aquecem separado)."""

    WARMUP_FILE = Path(__file__).parent.parent.parent / "warmup_state.json"

    @classmethod
    def _file(cls, channel: str = "whatsapp") -> Path:
        if channel == "whatsapp":
            return cls.WARMUP_FILE
        return cls.WARMUP_FILE.with_name(f"{cls.WARMUP_FILE.stem}_{channel}.json")

    @classmethod
    def _load_state(cls, channel: str = "whatsapp") -> dict:
        path = cls._file(channel)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"first_use_date": None, "total_sent": 0}

    @classmethod
    def _save_state(cls, state: dict, channel: str = "whatsapp"):
        cls._file(channel).write_text(json.dumps(state, indent=2), encoding="utf-8")

    @staticmethod
    def _curve_and_limit(channel: str) -> tuple[list[int], int]:
        if channel == "email":
            return settings.email_warmup_curve_list, settings.EMAIL_DAILY_LIMIT
        return settings.warmup_curve_list, settings.DAILY_SEND_LIMIT

    @classmethod
    def get_first_use_date(cls, channel: str = "whatsapp") -> datetime | None:
        state = cls._load_state(channel)
        if state.get("first_use_date"):
            return datetime.fromisoformat(state["first_use_date"])
        return None

    @classmethod
    def register_first_use(cls, channel: str = "whatsapp"):
        state = cls._load_state(channel)
        if not state.get("first_use_date"):
            state["first_use_date"] = datetime.now(timezone.utc).isoformat()
            cls._save_state(state, channel)

    @classmethod
    def get_max_today(cls, channel: str = "whatsapp") -> int:
        state = cls._load_state(channel)
        curve, limit = cls._curve_and_limit(channel)

        if not state.get("first_use_date"):
            return min(curve[0], limit) if curve else limit

        first_use = datetime.fromisoformat(state["first_use_date"])
        days_since = (datetime.now(timezone.utc) - first_use).days

        if days_since >= len(curve):
            return limit

        return min(curve[days_since], limit)

    @classmethod
    def get_day_number(cls, channel: str = "whatsapp") -> int:
        state = cls._load_state(channel)
        if not state.get("first_use_date"):
            return 1
        first_use = datetime.fromisoformat(state["first_use_date"])
        return (datetime.now(timezone.utc) - first_use).days + 1


class CollectionTracker:
    """Rastreia histórico de coletas automáticas para selecionar targets."""

    HISTORY_FILE = Path(__file__).parent.parent.parent / "collection_history.json"

    @classmethod
    def _load(cls) -> dict:
        if cls.HISTORY_FILE.exists():
            return json.loads(cls.HISTORY_FILE.read_text(encoding="utf-8"))
        return {"runs": []}

    @classmethod
    def _save(cls, data: dict):
        cls.HISTORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def get_targets(cls) -> list[dict]:
        if not _TARGETS_FILE.exists():
            return []
        with open(_TARGETS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("targets", [])

    @classmethod
    def record_run(cls, category_slug: str, city_name: str, stats: dict):
        data = cls._load()
        data["runs"].append({
            "category_slug": category_slug,
            "city_name": city_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "imported": stats.get("imported", 0),
        })
        cls._save(data)

    @classmethod
    def get_next_target(cls) -> dict | None:
        """Retorna o target menos usado recentemente, ou None se todos usados nos últimos N dias."""
        targets = cls.get_targets()
        if not targets:
            return None

        data = cls._load()
        runs = data.get("runs", [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=COLLECTION_COOLDOWN_DAYS)

        recent_keys = set()
        for run in runs:
            ts = datetime.fromisoformat(run["timestamp"])
            if ts >= cutoff:
                recent_keys.add(f"{run['category_slug']}:{run['city_name']}")

        unused = [t for t in targets if f"{t['category_slug']}:{t['city_name']}" not in recent_keys]

        if not unused:
            return None

        usage_count = {}
        for t in targets:
            key = f"{t['category_slug']}:{t['city_name']}"
            count = sum(1 for r in runs if f"{r['category_slug']}:{r['city_name']}" == key)
            usage_count[key] = count

        unused.sort(key=lambda t: usage_count.get(f"{t['category_slug']}:{t['city_name']}", 0))
        return unused[0]


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
            "email_warmup_day": WarmupManager.get_day_number("email"),
            "email_warmup_max_today": WarmupManager.get_max_today("email"),
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

    def _is_within_send_window(self, country: CountrySettings | None = None) -> bool:
        if country is None:
            now = datetime.now(BRT)
            start, end = settings.SEND_WINDOW_START, settings.SEND_WINDOW_END
        else:
            now = datetime.now(country.tz)
            start, end = country.send_window
        return start <= now.hour < end

    def _is_weekday(self, country: CountrySettings | None = None) -> bool:
        return datetime.now(country.tz if country else BRT).weekday() < 5

    def _sent_since(self, since_local: datetime, channel: str) -> int:
        return self.db.query(func.count(Message.id)).filter(
            Message.sent_at >= since_local.astimezone(timezone.utc),
            Message.status == "enviado",
            Message.channel == channel,
        ).scalar()

    def _can_send_hourly(self, channel: str = "whatsapp") -> bool:
        now = datetime.now(CHANNEL_TZ.get(channel, BRT))
        limit = settings.EMAIL_HOURLY_LIMIT if channel == "email" else settings.HOURLY_SEND_LIMIT
        return self._sent_since(now.replace(minute=0, second=0, microsecond=0), channel) < limit

    def _can_send_daily(self, channel: str = "whatsapp") -> bool:
        now = datetime.now(CHANNEL_TZ.get(channel, BRT))
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self._sent_since(day_start, channel) < WarmupManager.get_max_today(channel)

    def _check_opt_out(self, company: Company) -> bool:
        if company.phone:
            if self.db.query(OptOut).filter(OptOut.contact_identifier == company.phone).first():
                return True
        if company.instagram:
            if self.db.query(OptOut).filter(OptOut.contact_identifier == company.instagram).first():
                return True
        if company.email:
            if self.db.query(OptOut).filter(OptOut.contact_identifier == company.email.lower()).first():
                return True
        return False

    def _has_active_message(self, company_id: int) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return self.db.query(Message).filter(
            Message.company_id == company_id,
            Message.status == "enviado",
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
            .filter(ProspectingQueue.status.in_(_QUEUE_BLOCKING))
            .all()
        ]

        recent_msg_company_ids = [
            row[0] for row in self.db.query(Message.company_id)
            .filter(
                Message.generated_at >= cutoff,
                Message.status == "enviado",
            )
            .distinct()
            .all()
        ]

        exclude_ids = set(active_queue_company_ids + recent_msg_company_ids)

        # Telefone (WhatsApp), e-mail, ou site onde a auditoria pode achar o e-mail.
        companies = self.db.query(Company).filter(
            ((Company.phone.isnot(None)) & (Company.phone != ""))
            | ((Company.email.isnot(None)) & (Company.email != ""))
            | ((Company.website.isnot(None)) & (Company.website != ""))
        ).all()

        eligible = []
        for c in companies:
            if c.id in exclude_ids:
                continue
            if c.phone in opted_out_phones:
                continue
            if c.instagram and c.instagram in opted_out_phones:
                continue
            if c.email and c.email.lower() in opted_out_phones:
                continue
            eligible.append(c)

        return eligible[:AUTO_ENQUEUE_BATCH_SIZE]

    def _get_companies_without_phone(self) -> list[Company]:
        """Busca empresas sem telefone elegíveis para coleta de dados."""
        companies = self.db.query(Company).filter(
            (Company.phone.is_(None)) | (Company.phone == ""),
            Company.website.isnot(None),
            Company.website != "",
        ).limit(AUTO_ENQUEUE_BATCH_SIZE).all()
        return companies

    async def _run_auto_collection(self) -> int:
        """Dispara coleta Google Maps quando base está esgotada. Retorna empresas novas."""
        target = CollectionTracker.get_next_target()
        if not target:
            logger.info(
                "Nenhum alvo de coleta disponivel — configure novos targets"
            )
            return 0

        category_slug = target["category_slug"]
        city_name = target["city_name"]
        max_results = target.get("max_results", 20)

        logger.info(
            f"Base esgotada — disparando coleta: {category_slug} em {city_name}"
        )

        count_before = self.db.query(func.count(Company.id)).scalar()

        try:
            from app.collectors.google_maps import GoogleMapsCollector

            def run_sync():
                collector = GoogleMapsCollector(self.db)
                stats = collector.collect(
                    category_slug=category_slug,
                    city_name=city_name,
                    max_results=max_results,
                    headless=True,
                )
                self.db.commit()
                return stats

            loop = asyncio.get_event_loop()
            stats = await asyncio.wait_for(
                loop.run_in_executor(None, run_sync),
                timeout=COLLECTION_TIMEOUT_SECONDS,
            )

            count_after = self.db.query(func.count(Company.id)).scalar()
            new_count = count_after - count_before

            CollectionTracker.record_run(category_slug, city_name, stats)

            logger.info(
                f"Coleta concluida: {category_slug} em {city_name} — "
                f"{new_count} empresas novas (total: {count_after})"
            )
            return new_count

        except asyncio.TimeoutError:
            logger.warning(
                f"Coleta excedeu timeout ({COLLECTION_TIMEOUT_SECONDS}s): "
                f"{category_slug} em {city_name}"
            )
            return 0
        except Exception as e:
            logger.error(f"Erro na coleta automatica: {e}")
            return 0

    async def _try_auto_collect(self) -> int:
        """Tenta coleta automática se base esgotada. Retorna quantidade coletada."""
        target = CollectionTracker.get_next_target()
        if not target:
            return 0
        return await self._run_auto_collection()

    async def _prepare_company(self, company: Company) -> tuple[Audit | None, list[Opportunity]]:
        """Garante auditoria e oportunidades da empresa (roda o que faltar)."""
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

        return audit, opportunities

    async def _compose(
        self,
        company: Company,
        audit: Audit | None,
        opportunities: list[Opportunity],
        channel: str,
        country: CountrySettings,
    ) -> tuple[Message, str | None]:
        """Gera e valida a mensagem de outreach do canal. Retorna (msg salva, erro de validacao)."""
        from app.api.v1.endpoints.diagnosis import build_diagnosis

        diagnosis = build_diagnosis(company, audit, opportunities, self.db)
        subject, language = None, None

        if channel == "email":
            from app.i18n import legal_footer
            from app.llm.email_agent import generate_outreach_email
            from app.sending.email_validator import validate_email

            language = country.resolve_language(audit.site_lang if audit else None)
            draft = await generate_outreach_email(company, audit, opportunities, diagnosis, language)
            if draft is None:
                message_text, error = "", "Sem dado concreto da auditoria para citar"
            else:
                subject = draft.subject
                _, error = validate_email(draft.subject, draft.body, company.name)
                message_text = draft.body + "\n\n" + legal_footer(
                    language, settings.SENDER_BRAND, settings.SENDER_POSTAL_ADDRESS, company.name,
                    settings.SENDER_CONTACT_NAME, settings.SENDER_WEBSITE,
                )
        else:
            from app.llm.sales_agent import generate_outreach_message

            message_text = await generate_outreach_message(company, audit, opportunities, diagnosis)
            _, error = ContentValidator.validate(message_text, company.name, audit, opportunities)

        now = datetime.now(timezone.utc)
        msg = Message(
            company_id=company.id,
            opportunity_ids=json.dumps([o.id for o in opportunities[:3]]),
            message_text=message_text,
            channel=channel,
            message_type="outreach",
            subject=subject,
            language=language,
            status="erro_validacao" if error else "aprovado",
            generated_at=now,
            approved_at=None if error else now,
            last_error=error,
            llm_model=settings.LLM_MODEL,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        if error:
            logger.warning(f"Validacao falhou para {company.name} ({channel}): {error}")
        return msg, error

    def _upsert_queue(self, company_id: int, status: str, notes: str):
        entry = self.db.query(ProspectingQueue).filter(ProspectingQueue.company_id == company_id).first()
        if entry:
            entry.status = status
            entry.notes = notes
            entry.updated_at = datetime.now(timezone.utc)
        else:
            self.db.add(ProspectingQueue(company_id=company_id, status=status, notes=notes))
        self.db.commit()

    def _country_of(self, company: Company) -> CountrySettings | None:
        try:
            return get_country(country_code_for_company(company))
        except KeyError:
            return None

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

                valid, error = ContentValidator.validate(
                    message_text, company.name, audit, opportunities
                )
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

        channel = company.preferred_channel or "whatsapp"

        # Reaproveita a mensagem aprovada no auto-enqueue (evita segunda chamada ao LLM).
        msg = self.db.query(Message).filter(
            Message.company_id == company.id,
            Message.status == "aprovado",
            Message.message_type == "outreach",
            Message.channel == channel,
        ).order_by(Message.id.desc()).first()

        if msg is None:
            country = self._country_of(company) or get_country("BR")
            audit, opportunities = await self._prepare_company(company)
            msg, error = await self._compose(company, audit, opportunities, channel, country)
            if error:
                return False

        return await self._send_message(msg, company)

    async def _deliver(self, msg: Message, company: Company) -> tuple[dict | None, str | None]:
        """Entrega pelo canal da mensagem. Retorna (resultado, contato); resultado None = canal indisponivel."""
        if msg.channel == "email":
            from app.sending.email_client import EmailSender

            sender = EmailSender()
            if not await sender.is_configured():
                logger.warning("E-mail nao configurado (.env) — envio adiado")
                return None, company.email
            result = await sender.send(company.email, msg.subject, msg.message_text)
            msg.thread_id = result["message_id"]
            return result, company.email

        from app.sending.whatsapp_client import WhatsAppClient

        client = WhatsAppClient()
        if not await client.is_connected():
            logger.warning("WhatsApp nao conectado")
            return None, company.phone
        result = await client.send(company.phone, msg.message_text)
        return result, company.phone

    async def _send_message(self, msg: Message, company: Company) -> bool:
        """Envia a mensagem pelo canal dela e registra o resultado."""
        contact = company.email if msg.channel == "email" else company.phone
        try:
            result, contact = await self._deliver(msg, company)
            if result is None:
                return False

            msg.status = "enviado"
            msg.sent_at = datetime.now(timezone.utc)
            msg.send_attempts = (msg.send_attempts or 0) + 1
            msg.last_error = None
            self.db.commit()

            WarmupManager.register_first_use(msg.channel)

            country = self._country_of(company)
            log_entry = ActionLog(
                company_id=company.id,
                contact_id=contact,
                action="mensagem_enviada",
                details=json.dumps({
                    "message_id": msg.id,
                    "channel": msg.channel,
                    "legal_basis": country.legal_basis if country else None,
                    "result": result,
                }, default=str),
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
            logger.info(f"Mensagem enviada para {company.name} ({msg.channel}: {contact})")
            return True

        except Exception as e:
            msg.status = "erro_envio"
            msg.send_attempts = (msg.send_attempts or 0) + 1
            msg.last_error = str(e)
            self.db.commit()

            self._consecutive_errors += 1
            self._last_error = str(e)
            self._check_circuit_breaker()

            log_entry = ActionLog(
                company_id=company.id,
                contact_id=contact,
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

        self._running = True
        self._last_cycle_at = datetime.now(timezone.utc)
        logger.info("Ciclo do dispatcher iniciado")

        try:
            enqueued = await self._auto_enqueue()
            logger.info(f"Novas empresas processadas: {enqueued}")

            if enqueued == 0:
                collected = await self._try_auto_collect()
                if collected > 0:
                    enqueued = await self._auto_enqueue()
                    logger.info(f"Pos-coleta — empresas processadas: {enqueued}")

            if not self._is_within_send_window():
                logger.info("Fora da janela de envio — skip envio, auto-enqueue concluido")
                return

            if not self._can_send_daily():
                logger.info("Limite diario atingido — skip envio")
                return

            if not self._can_send_hourly():
                logger.info("Limite horario atingido — skip envio")
                return

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
