"""Decide o canal de contato de uma empresa. Deterministico, sem LLM.

A decisao e congelada em Company.preferred_channel no primeiro enfileiramento:
outreach e follow-up saem sempre pelo mesmo canal.
"""

from app.core.countries import CountrySettings
from app.prospecting.email_policy import check_email_eligibility


def decide_channel(company, audit, country: CountrySettings) -> tuple[str | None, str | None]:
    """Retorna (canal, motivo). Canal None = empresa nao elegivel para contato automatico."""
    if not country.outreach_enabled:
        return None, f"outreach desligado para {country.code}"

    reasons = []

    if "whatsapp" in country.channels and company.phone:
        has_signal = bool(audit and (audit.whatsapp_catalog_link or audit.whatsapp_responds_badge))
        if has_signal or "email" not in country.channels:
            return "whatsapp", None

    if "email" in country.channels:
        ok, reason = check_email_eligibility(company, audit, country)
        if ok:
            return "email", None
        reasons.append(reason)

    if "whatsapp" in country.channels and company.phone:
        return "whatsapp", None

    if "whatsapp" in country.channels and not company.phone:
        reasons.append("sem telefone")

    return None, "; ".join(r for r in reasons if r) or "nenhum canal disponivel"


def resolve_channel(company, audit, country: CountrySettings) -> tuple[str | None, str | None]:
    """Respeita o canal ja congelado; so decide se ainda nao houver."""
    if company.preferred_channel:
        if company.preferred_channel not in country.channels:
            return None, f"canal {company.preferred_channel} nao habilitado para {country.code}"
        return company.preferred_channel, None
    channel, reason = decide_channel(company, audit, country)
    if channel:
        company.preferred_channel = channel
    return channel, reason
