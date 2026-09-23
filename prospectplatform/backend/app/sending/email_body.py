"""Fecha o corpo do e-mail como uma pessoa fecharia: primeiro nome, depois o rodape legal."""

from app.core.config import settings
from app.i18n import legal_footer


def signature_name() -> str:
    """Primeiro nome de quem assina. Sem nome de contato, assina com a marca."""
    contact = (settings.SENDER_CONTACT_NAME or "").strip()
    return contact.split()[0] if contact else (settings.SENDER_BRAND or "").strip()


def finish_email(body: str, language: str | None, company_name: str) -> str:
    parts = [body.strip()]
    name = signature_name()
    if name:
        parts.append(name)
    parts.append(legal_footer(language, settings.SENDER_BRAND, settings.SENDER_POSTAL_ADDRESS, company_name,
                              settings.SENDER_CONTACT_NAME, settings.SENDER_WEBSITE))
    return "\n\n".join(parts)
