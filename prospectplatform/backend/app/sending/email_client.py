"""Envio de e-mail via SMTP (Gmail com senha de app). Texto puro, sem tracking."""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.core.config import settings


class EmailSender:
    """Mesma forma do WhatsAppClient: send() + is_configured()."""

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.address = settings.EMAIL_ADDRESS
        self.password = settings.EMAIL_APP_PASSWORD
        self.display_name = settings.SENDER_CONTACT_NAME or settings.SENDER_BRAND

    async def is_configured(self) -> bool:
        return settings.email_configured

    def build_message(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = formataddr((self.display_name, self.address))
        msg["To"] = to
        msg["Subject"] = subject
        domain = self.address.split("@", 1)[-1] or None
        msg["Message-ID"] = make_msgid(domain=domain)
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = f"{references} {in_reply_to}".strip() if references else in_reply_to
        # Descadastro em um clique pelo cliente de e-mail (RFC 2369): cai na nossa caixa e o IMAP registra.
        msg["List-Unsubscribe"] = f"<mailto:{self.address}?subject=STOP>"
        msg.set_content(body)
        return msg

    def _send_sync(self, msg: EmailMessage):
        context = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=60) as smtp:
                smtp.login(self.address, self.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=60) as smtp:
                smtp.starttls(context=context)
                smtp.login(self.address, self.password)
                smtp.send_message(msg)

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict:
        if not await self.is_configured():
            raise RuntimeError(
                "E-mail nao configurado: defina EMAIL_ADDRESS, EMAIL_APP_PASSWORD, "
                "SENDER_BRAND e SENDER_POSTAL_ADDRESS no .env"
            )
        msg = self.build_message(to, subject, body, in_reply_to, references)
        await asyncio.to_thread(self._send_sync, msg)
        return {"message_id": msg["Message-ID"], "to": to}
