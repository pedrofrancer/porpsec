"""Gera o e-mail frio de abordagem (assunto + corpo) no idioma da empresa."""

import json
import re

from app.core.config import settings
from app.core.countries import search_term
from app.i18n import LANGUAGE_NAMES, lang_key
from app.llm.client import LLMClient
from app.llm.sales_agent import _build_context

SYSTEM_PROMPT = """You write short cold emails to owners of small local businesses in Europe, offering to build or rebuild their website.
You write like one real freelancer writing to one business owner: plain, specific, polite, never salesy.

HARD RULES (all mandatory):
1. Write ONLY in {language_name}. Use the formal-but-warm register ({formality}).
2. Mention the exact business name "{company_name}" in the body.
3. Cite ONE or TWO concrete facts from the audit data below (e.g. the site does not open well on mobile, it takes N seconds to load, there is no online booking, no HTTPS). Never invent a fact that is not in the data. If there is no concrete fact, answer exactly: INSUFFICIENT_DATA
4. Offer to show a ready preview of how their new site could look, built with their own name, colours and photos. {price_rule}
5. Body: 60 to 130 words, 2 or 3 short paragraphs, plain text. No links, no emojis, no markdown, no bullet lists, no signature, no greeting line like "I hope this email finds you well".
6. Subject: 3 to 8 words, lowercase except proper nouns, specific to the business, no clickbait, no "!".
7. Vary the opening: do not always start with "I saw" / "J'ai vu" / "Ik zag".

Answer with a JSON object only: {{"subject": "...", "body": "..."}}
"""

_FORMALITY = {
    "fr": 'vouvoiement, "vous"',
    "nl": 'formal "u"',
    "pt": 'tratamento formal leve, "o senhor/a senhora" ou "voces", portugues de Portugal (nunca brasileiro)',
    "en": "polite, first-name-free",
}

_PRICE_RULE = {
    True: 'Mention once, naturally, that a site like this starts at "{price}".',
    False: "Do not mention prices.",
}


class EmailDraft:
    def __init__(self, subject: str, body: str):
        self.subject = subject.strip()
        self.body = body.strip()

    def __repr__(self):
        return f"EmailDraft(subject={self.subject!r})"


def _parse_llm_json(raw: str) -> EmailDraft | None:
    if raw.strip() == "INSUFFICIENT_DATA":
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    subject, body = data.get("subject"), data.get("body")
    if not subject or not body:
        return None
    return EmailDraft(subject, body)


async def generate_outreach_email(company, audit, opportunities, diagnosis, language: str) -> EmailDraft | None:
    """Retorna None quando nao ha dado concreto para citar (empresa fica sem envio)."""
    key = lang_key(language)
    client = LLMClient()
    if not client.is_configured:
        return fallback_email(company, audit, language)

    price = settings.OFFER_PRICE_RANGE.strip()
    system = SYSTEM_PROMPT.format(
        language_name=LANGUAGE_NAMES.get(key, "English"),
        formality=_FORMALITY.get(key, _FORMALITY["en"]),
        company_name=company.name,
        price_rule=_PRICE_RULE[bool(price)].format(price=price),
    )
    context = _build_context(company, audit, opportunities, diagnosis)
    user = (
        "Business data (field labels are in Portuguese; the email must be in the target language):\n"
        f"{context}"
    )
    raw = await client.chat(system, user, temperature=0.8)
    return _parse_llm_json(raw)


# --- fallback sem LLM: frases fixas por idioma, uma por sinal da auditoria ---

_FALLBACK = {
    "fr": {
        "subject": "le site de {name}",
        "mobile": "votre site s'affiche mal sur téléphone",
        "slow": "votre site met plus de {secs} secondes à charger",
        "booking": "on ne peut pas réserver en ligne sur votre site",
        "https": "votre site n'est pas en HTTPS, le navigateur affiche « non sécurisé »",
        "body": "Bonjour,\n\nEn cherchant {category} à {city}, je suis tombé sur {name} : {fact}. "
                "Beaucoup de clients abandonnent à ce moment-là.\n\n"
                "Je peux vous envoyer un aperçu de ce que pourrait être votre nouveau site, avec votre nom, "
                "vos couleurs et vos photos.{price} Cela vous intéresse ?",
        "price": " Ce type de site commence à {price}.",
    },
    "nl": {
        "subject": "de website van {name}",
        "mobile": "uw website werkt niet goed op de telefoon",
        "slow": "uw website laadt pas na {secs} seconden",
        "booking": "op uw website kunt u niet online boeken",
        "https": "uw website heeft geen HTTPS, de browser toont 'niet veilig'",
        "body": "Goedendag,\n\nToen ik zocht naar {category} in {city}, kwam ik {name} tegen: {fact}. "
                "Veel klanten haken op dat moment af.\n\n"
                "Ik kan u een voorbeeld sturen van hoe uw nieuwe website eruit kan zien, met uw naam, "
                "kleuren en foto's.{price} Zou u dat willen zien?",
        "price": " Zo'n website begint bij {price}.",
    },
    "pt": {
        "subject": "o site da {name}",
        "mobile": "o vosso site não abre bem no telemóvel",
        "slow": "o vosso site demora mais de {secs} segundos a carregar",
        "booking": "não é possível marcar online no vosso site",
        "https": "o vosso site não tem HTTPS e o browser mostra 'não seguro'",
        "body": "Bom dia,\n\nAo procurar {category} em {city}, encontrei a {name}: {fact}. "
                "Muitos clientes desistem nesse momento.\n\n"
                "Posso enviar-lhe uma pré-visualização de como ficaria o novo site, com o vosso nome, "
                "cores e fotografias.{price} Tem interesse em ver?",
        "price": " Um site assim começa em {price}.",
    },
}


def fallback_email(company, audit, language: str) -> EmailDraft | None:
    texts = _FALLBACK.get(lang_key(language))
    if not texts or not audit:
        return None
    fmt = {"name": company.name}
    if audit.has_viewport is False:
        fact = texts["mobile"].format(**fmt)
    elif audit.response_time_ms and audit.response_time_ms >= 4000:
        fact = texts["slow"].format(secs=audit.response_time_ms // 1000, **fmt)
    elif audit.has_scheduling is False:
        fact = texts["booking"].format(**fmt)
    elif audit.has_https is False:
        fact = texts["https"].format(**fmt)
    else:
        return None
    price = settings.OFFER_PRICE_RANGE.strip()
    body = texts["body"].format(
        category=(search_term(company.category.slug, company.category.name, language) if company.category else ""),
        city=company.city.name if company.city else "",
        name=company.name,
        fact=fact,
        price=texts["price"].format(price=price) if price else "",
    )
    return EmailDraft(texts["subject"].format(**fmt), body)
