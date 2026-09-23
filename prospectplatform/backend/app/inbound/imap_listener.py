"""Le a caixa do Gmail por IMAP e entrega os e-mails novos ao ReplyEventHandler.

Polling curto (IMAP_POLL_SECONDS) em vez de IDLE: mais simples, sobrevive a queda de rede
e ao PC dormindo, e ainda fica bem abaixo da meta de 5 minutos. Usa BODY.PEEK, entao nao
marca nada como lido na caixa.
"""

import asyncio
import imaplib
import logging
from datetime import datetime, timedelta, timezone

from app.core.background import StopSignal, graceful_stop
from app.core.config import settings
from app.inbound.email_parser import MSGID_RE, parse_email
from app.models.inbound import InboundReply

logger = logging.getLogger("inbound")

LOOKBACK_DAYS = 14


class ImapReplyListener:
    def __init__(self, handler_factory):
        # handler_factory() -> (ReplyEventHandler, db_session); a sessao e fechada a cada poll.
        self.handler_factory = handler_factory
        self._task: asyncio.Task | None = None
        self._stop = StopSignal()
        self.last_poll_at: datetime | None = None
        self.last_error: str | None = None
        self._not_ours: set[str] = set()  # e-mails da caixa que nao sao resposta a outreach

    @property
    def configured(self) -> bool:
        return bool(settings.EMAIL_ADDRESS and settings.EMAIL_APP_PASSWORD)

    def _search_recent(self, imap) -> list[bytes]:
        since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
        imap.select("INBOX", readonly=True)
        status, data = imap.search(None, "SINCE", since)
        return data[0].split() if status == "OK" and data and data[0] else []

    @staticmethod
    def _header_message_id(imap, num: bytes) -> str | None:
        status, parts = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
        if status != "OK" or not parts or not isinstance(parts[0], tuple):
            return None
        match = MSGID_RE.search(parts[0][1].decode("utf-8", errors="replace"))
        return match.group(0) if match else None

    def poll_once(self) -> int:
        """Processa a janela recente da caixa. Retorna quantos e-mails novos foram registrados.

        Busca so o cabecalho Message-ID de cada e-mail e baixa o corpo apenas dos ainda nao vistos.
        """
        handler, db = self.handler_factory()
        registered = 0
        try:
            known = {row[0] for row in db.query(InboundReply.external_id).all()}
            with imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT) as imap:
                imap.login(settings.EMAIL_ADDRESS, settings.EMAIL_APP_PASSWORD)
                for num in self._search_recent(imap):
                    mid = self._header_message_id(imap, num)
                    if mid and (mid in known or mid in self._not_ours):
                        continue
                    status, parts = imap.fetch(num, "(BODY.PEEK[])")
                    if status != "OK" or not parts or not isinstance(parts[0], tuple):
                        continue
                    try:
                        if handler.handle(parse_email(parts[0][1])):
                            registered += 1
                        elif mid:
                            self._not_ours.add(mid)
                    except Exception as e:
                        db.rollback()
                        logger.warning(f"E-mail ignorado (erro no parse/registro): {e}")
        finally:
            db.close()
        self.last_poll_at = datetime.now(timezone.utc)
        return registered

    async def run_loop(self):
        if not self.configured:
            logger.info("IMAP nao configurado (.env) — leitura de respostas desligada")
            return
        logger.info(f"Leitura de respostas por IMAP a cada {settings.IMAP_POLL_SECONDS}s")
        while not self._stop.requested:
            try:
                count = await asyncio.to_thread(self.poll_once)
                self.last_error = None
                if count:
                    logger.info(f"{count} e-mail(s) novo(s) registrado(s)")
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Falha na leitura IMAP: {e}")
            if await self._stop.sleep(settings.IMAP_POLL_SECONDS):
                break

    def start(self):
        self._task = asyncio.create_task(self.run_loop())

    async def shutdown(self):
        await graceful_stop(self._task, self._stop, "Leitura IMAP")
        self._task = None

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    @property
    def status(self) -> dict:
        return {
            "configured": self.configured,
            "running": self._task is not None and not self._task.done(),
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "last_error": self.last_error,
        }
