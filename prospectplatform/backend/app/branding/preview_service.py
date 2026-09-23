"""Ciclo da previa: primeira resposta -> rascunho -> (aprovacao) -> publicacao -> follow-up no thread."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.branding import brand_kit
from app.branding.publisher import PagesPublisher, make_slug
from app.branding.site_renderer import render_site
from app.core.config import settings
from app.core.countries import country_code_for_company, get_country
from app.i18n import legal_footer
from app.llm.followup_agent import compose_followup, validate_followup
from app.models.audit import Audit
from app.models.inbound import InboundReply
from app.models.message import Message
from app.models.preview import SitePreview
from app.models.prospection import ActionLog, OptOut, ProspectingQueue

logger = logging.getLogger("previews")

ACTIVE = ("pendente", "rascunho", "publicado", "enviado")


class PreviewError(RuntimeError):
    pass


def enqueue_for_reply(db: Session, reply: InboundReply, company, outreach: Message) -> SitePreview | None:
    """Gancho da primeira resposta: so cria o pedido; o trabalho pesado roda no PreviewWorker."""
    existing = db.query(SitePreview).filter(
        SitePreview.company_id == company.id, SitePreview.status.in_(ACTIVE)
    ).first()
    if existing:
        return None
    preview = SitePreview(company_id=company.id, reply_id=reply.id, slug=make_slug(company.name),
                          status="pendente", language=outreach.language)
    db.add(preview)
    db.commit()
    logger.info(f"Previa pedida para {company.name}")
    return preview


class PreviewService:
    def __init__(self, db: Session, publisher: PagesPublisher | None = None, sender=None):
        self.db = db
        self.publisher = publisher or PagesPublisher()
        self._sender = sender

    @property
    def sender(self):
        if self._sender is None:
            from app.sending.email_client import EmailSender
            self._sender = EmailSender()
        return self._sender

    def _language(self, preview: SitePreview, company, audit) -> str:
        if preview.language:
            return preview.language
        try:
            country = get_country(country_code_for_company(company))
            return country.resolve_language(audit.site_lang if audit else None)
        except KeyError:
            return "en"

    async def build_draft(self, preview: SitePreview) -> SitePreview:
        company = preview.company
        audit = self.db.query(Audit).filter(Audit.company_id == company.id).order_by(Audit.id.desc()).first()
        language = self._language(preview, company, audit)

        # So a chamada HTTP das fotos vai para thread; a sessao do banco fica nesta.
        photos = await asyncio.to_thread(brand_kit.pexels_photos, brand_kit.photo_query_for(company), 4)
        kit = brand_kit.build_brand_kit(company, audit, language, photo_source=lambda q, n: photos[:n])
        html = render_site(kit, settings.SENDER_BRAND)
        self.publisher.write(preview.slug, html)

        url = self.publisher.public_url(preview.slug)
        reply = preview.reply
        outreach = reply.message if reply else None
        text = await compose_followup(company.name, reply.raw_content if reply else "", language, url,
                                      kit.brand_colors_from_site, settings.OFFER_PRICE_RANGE.strip())

        preview.language = language
        preview.template_slug = f"{kit.category_slug}:{kit.mood}"
        preview.brand_kit_json = kit.to_json()
        preview.html = html
        preview.preview_url = url
        subject = (outreach.subject if outreach and outreach.subject else company.name)
        preview.followup_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        preview.followup_text = text
        preview.status = "rascunho"
        preview.last_error = None
        preview.generated_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.info(f"Previa em rascunho: {company.name} ({preview.slug})")
        return preview

    def _is_blocked(self, company, reply) -> bool:
        ids = [x.lower() for x in (company.email, reply.from_address if reply else None) if x]
        return bool(ids and self.db.query(OptOut).filter(OptOut.contact_identifier.in_(ids)).first())

    async def approve(self, preview: SitePreview, subject: str | None = None, text: str | None = None) -> SitePreview:
        """Publica a previa e responde no mesmo thread do e-mail da empresa."""
        if preview.status not in ("rascunho", "publicado"):
            raise PreviewError(f"Previa em '{preview.status}' nao pode ser enviada")
        if subject:
            preview.followup_subject = subject.strip()
        if text:
            preview.followup_text = text.strip()
        ok, error = validate_followup(preview.followup_text, preview.preview_url)
        if not ok:
            raise PreviewError(error)

        company, reply = preview.company, preview.reply
        if self._is_blocked(company, reply):
            raise PreviewError("Empresa pediu para nao receber mais mensagens (opt-out)")
        if not await self.sender.is_configured():
            raise PreviewError("E-mail nao configurado no .env")

        if preview.status == "rascunho":
            await asyncio.to_thread(self.publisher.deploy)
            preview.status = "publicado"
            preview.published_at = datetime.now(timezone.utc)
            preview.expires_at = preview.published_at + timedelta(days=settings.PREVIEW_TTL_DAYS)
            self.db.commit()

        outreach = reply.message if reply else None
        body = preview.followup_text + "\n\n" + legal_footer(
            preview.language, settings.SENDER_BRAND, settings.SENDER_POSTAL_ADDRESS, company.name,
            settings.SENDER_CONTACT_NAME, settings.SENDER_WEBSITE)
        to = (reply.from_address if reply and reply.from_address else company.email)
        result = await self.sender.send(
            to, preview.followup_subject, body,
            in_reply_to=reply.external_id if reply and not reply.external_id.startswith("noid:") else None,
            references=outreach.thread_id if outreach else None,
        )

        now = datetime.now(timezone.utc)
        msg = Message(company_id=company.id, opportunity_ids="[]", message_text=body, channel="email",
                      message_type="template_followup", subject=preview.followup_subject,
                      language=preview.language, status="enviado", generated_at=now, approved_at=now,
                      sent_at=now, send_attempts=1, thread_id=result["message_id"], llm_model=settings.LLM_MODEL)
        self.db.add(msg)
        self.db.flush()
        preview.followup_message_id = msg.id
        preview.status = "enviado"
        preview.sent_at = now
        if reply:
            reply.resulted_in_template = True
        queue = self.db.query(ProspectingQueue).filter(ProspectingQueue.company_id == company.id).first()
        if queue:
            queue.status = "PREVIA_ENVIADA"
        self.db.add(ActionLog(company_id=company.id, contact_id=to, action="previa_enviada",
                              details=json.dumps({"preview_id": preview.id, "url": preview.preview_url})))
        self.db.commit()
        logger.info(f"Previa enviada para {company.name}: {preview.preview_url}")
        return preview

    def discard(self, preview: SitePreview):
        preview.status = "descartado"
        self.publisher.remove([preview.slug])
        self.db.commit()

    def reset(self, preview: SitePreview):
        if preview.status not in ("rascunho", "erro"):
            raise PreviewError("So da para gerar de novo um rascunho ainda nao publicado")
        preview.status = "pendente"
        self.db.commit()

    async def process_pending(self) -> int:
        pending = self.db.query(SitePreview).filter(SitePreview.status == "pendente").all()
        for preview in pending:
            try:
                await self.build_draft(preview)
                if settings.PREVIEW_AUTO_SEND:
                    await self.approve(preview)
            except Exception as e:
                self.db.rollback()
                preview.status = "erro" if preview.status == "pendente" else preview.status
                preview.last_error = str(e)[:2000]
                self.db.commit()
                logger.error(f"Previa {preview.slug} falhou: {e}")
        return len(pending)

    def expire_old(self) -> int:
        now = datetime.now(timezone.utc)
        expired = [p for p in self.db.query(SitePreview).filter(SitePreview.status.in_(("publicado", "enviado"))).all()
                   if p.expires_at and _aware(p.expires_at) < now]
        if not expired:
            return 0
        self.publisher.remove([p.slug for p in expired])
        for p in expired:
            p.status = "expirado"
        self.db.commit()
        if self.publisher.configured:
            self.publisher.deploy()
        return len(expired)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class PreviewWorker:
    """Loop de fundo: transforma pedidos pendentes em rascunho e expira previas vencidas."""

    INTERVAL_SECONDS = 30

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._last_expire: datetime | None = None

    async def tick(self):
        db = self.session_factory()
        try:
            service = PreviewService(db)
            await service.process_pending()
            now = datetime.now(timezone.utc)
            if not self._last_expire or now - self._last_expire > timedelta(hours=12):
                await asyncio.to_thread(service.expire_old)
                self._last_expire = now
        finally:
            db.close()

    async def run_loop(self):
        while True:
            try:
                await self.tick()
            except Exception as e:
                logger.error(f"PreviewWorker: {e}", exc_info=True)
            await asyncio.sleep(self.INTERVAL_SECONDS)

    def start(self):
        self._task = asyncio.create_task(self.run_loop())

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
