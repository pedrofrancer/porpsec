"""Resposta a quem respondeu o outreach, levando o link da previa.

Tem que parecer a continuacao da conversa, nao um disparo: responde primeiro ao que a pessoa
escreveu, diz com franqueza o que e o link, e termina com uma pergunta facil.
"""

import re

from app.core.config import settings
from app.i18n import LANGUAGE_NAMES, lang_key
from app.llm.client import LLMClient
from app.sending.email_validator import AI_TELLS

SYSTEM_PROMPT = """You are {sender}, an independent web developer. A few days ago you emailed {company_name} about their website. They just replied. Write your answer, in {language_name}, register: {formality}. It must read like the natural next message in a conversation between two people.

HOW TO WRITE IT:
1. First, respond to what they actually wrote, in one or two sentences. If they asked who you are, say it simply (your first name, independent web developer, you came across their site while looking for businesses like theirs). If they asked the price, answer it. If they were curious or said yes, just thank them briefly. Never ignore their message and never answer something they did not ask.
2. Then give the link, alone on its own line: {url}
3. Say honestly what it is: a first draft built from what is public on their site{colors_clause}, not online for their customers, easy to change.
4. {price_rule}
5. End with one short, easy question (for example whether a quick call this week would suit them, or what they would change first).

RULES: 40 to 100 words. Plain text. No emojis, no markdown, no exclamation marks. Do not sign and do not add a closing formula (added automatically). Never use "I hope", "don't hesitate", "solution", "online presence", "boost", or their equivalents. Answer with the email body only.
"""

_FORMALITY = {"fr": 'vouvoiement ("vous")', "nl": 'formeel "u"',
              "pt": "portugues de Portugal, formal leve", "en": "polite, warm"}

_FALLBACK = {
    "fr": "Merci pour votre réponse.\n\nJ'ai préparé un premier jet pour {name}, fait à partir de ce qui est public "
          "sur votre site, avec votre nom{colors} :\n{url}\n\nIl n'est pas en ligne pour vos clients et tout se "
          "change facilement. {price}Ça vous dirait qu'on en parle dix minutes cette semaine ?",
    "nl": "Dank u voor uw reactie.\n\nIk heb een eerste versie gemaakt voor {name}, op basis van wat openbaar op uw "
          "site staat, met uw naam{colors}:\n{url}\n\nDeze staat niet online voor uw klanten en alles is makkelijk "
          "aan te passen. {price}Zullen we deze week tien minuten bellen?",
    "pt": "Obrigado pela resposta.\n\nPreparei uma primeira versão para a {name}, feita a partir do que está público "
          "no vosso site, com o vosso nome{colors}:\n{url}\n\nNão está online para os clientes e muda-se tudo "
          "facilmente. {price}Dava jeito falarmos dez minutos esta semana?",
    "en": "Thanks for getting back to me.\n\nI put together a first draft for {name}, built from what is public on "
          "your site, with your name{colors}:\n{url}\n\nIt is not live for your customers and everything is easy to "
          "change. {price}Would a ten minute call this week suit you?",
}
_COLORS = {"fr": " et vos couleurs", "nl": " en uw kleuren", "pt": " e as vossas cores", "en": " and your colours"}
_PRICE = {"fr": "Un site comme celui-ci commence à {p}. ", "nl": "Een website als deze begint bij {p}. ",
          "pt": "Um site assim começa em {p}. ", "en": "A site like this starts at {p}. "}


def validate_followup(body: str | None, url: str) -> tuple[bool, str | None]:
    if not body or not body.strip():
        return False, "Follow-up vazio"
    if url not in body:
        return False, "Follow-up sem o link da previa"
    if len(body.split()) > 160:
        return False, "Follow-up longo demais"
    allowed = {url, url.rstrip("/")}
    other_links = [u for u in re.findall(r"https?://\S+", body) if u.rstrip(".,;:)") not in allowed]
    if other_links:
        return False, "Follow-up com link que nao e o da previa"
    low = body.lower()
    for tell in AI_TELLS:
        if re.search(tell, low):
            return False, f"Frase com cara de texto automatico: {tell}"
    return True, None


def fallback_followup(company_name: str, language: str, url: str, brand_colors: bool, price: str) -> str:
    key = lang_key(language)
    return _FALLBACK[key].format(
        name=company_name, url=url,
        colors=_COLORS[key] if brand_colors else "",
        price=_PRICE[key].format(p=price) if price else "",
    )


def _sender_first_name() -> str:
    contact = (settings.SENDER_CONTACT_NAME or "").strip()
    return contact.split()[0] if contact else "a freelance web developer"


async def compose_followup(company_name: str, reply_text: str, language: str, url: str,
                           brand_colors: bool, price: str) -> str:
    key = lang_key(language)
    client = LLMClient()
    if client.is_configured:
        system = SYSTEM_PROMPT.format(
            sender=_sender_first_name(),
            company_name=company_name,
            language_name=LANGUAGE_NAMES.get(key, "English"),
            formality=_FORMALITY.get(key, "polite"),
            url=url,
            colors_clause=" and the colours of their current website" if brand_colors else "",
            price_rule=(f'If they asked about price, say it starts at "{price}"; otherwise do not mention it.'
                        if price else "Do not mention prices."),
        )
        body = (await client.chat(system, f"Their reply:\n{reply_text[:1500]}", temperature=0.75)).strip()
        if validate_followup(body, url)[0]:
            return body
    return fallback_followup(company_name, language, url, brand_colors, price)
