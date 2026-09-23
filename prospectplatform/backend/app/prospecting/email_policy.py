"""Regras de quem pode receber e-mail frio (B2B, por pais).

Aceita so caixa da propria empresa: dominio igual ao do site, nada de webmail
e nada que pareca e-mail de uma pessoa (pessoa singular exige consentimento).
"""

import re

from app.auditors.extractors import (
    NL_LEGAL_ENTITIES,
    is_generic_local_part,
    is_webmail,
    registrable_domain,
)
from app.core.countries import CountrySettings


def _looks_like_brand_mailbox(email: str) -> bool:
    """salonlumiere@salonlumiere.fr: caixa com o nome da propria marca/dominio."""
    local = re.sub(r"[^a-z0-9]", "", email.split("@", 1)[0].lower())
    domain_label = re.sub(r"[^a-z0-9]", "", (registrable_domain(email) or "").split(".")[0])
    return bool(local and domain_label) and (local in domain_label or domain_label in local)


def check_email_eligibility(company, audit, country: CountrySettings) -> tuple[bool, str | None]:
    """Retorna (elegivel, motivo_da_recusa)."""
    if not country.outreach_enabled:
        return False, f"outreach desligado para {country.code}"
    if "email" not in country.channels:
        return False, f"canal email nao habilitado para {country.code}"

    email = (company.email or "").strip().lower()
    if not email or "@" not in email:
        return False, "sem e-mail"
    if is_webmail(email):
        return False, "e-mail de webmail (provavel pessoa fisica)"

    site_domain = registrable_domain(company.website)
    if not site_domain:
        return False, "sem site para confirmar o dominio do e-mail"
    if registrable_domain(email) != site_domain:
        return False, "e-mail fora do dominio do site da empresa"

    if not (is_generic_local_part(email) or _looks_like_brand_mailbox(email)):
        return False, "e-mail parece pessoal (nome de pessoa)"

    if country.require_legal_entity:
        signal = getattr(audit, "legal_entity_signal", None) if audit else None
        if signal not in NL_LEGAL_ENTITIES:
            return False, "sem sinal de pessoa juridica (B.V./N.V.) no site"

    return True, None
