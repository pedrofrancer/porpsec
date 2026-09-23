"""Resposta curta a quem respondeu o outreach, levando o link da previa."""

import re

from app.i18n import LANGUAGE_NAMES, lang_key
from app.llm.client import LLMClient
from app.sending.email_validator import AI_TELLS

SYSTEM_PROMPT = """You are the same freelancer who emailed {company_name} a few days ago. They just replied.
Write your answer to their reply, in {language_name}, formal-but-warm register ({formality}).

RULES:
1. React to what they actually wrote (a question, a "who are you?", a "yes, show me", a doubt). Do not ignore it.
2. Include this exact link once, on its own line: {url}
3. Say plainly that it is a first preview built with their name{colors_clause}, and that it is not online for their customers.
4. {price_rule}
5. 40 to 110 words. Plain text. No emojis, no markdown, no signature, no greeting cliches, no "I hope".
6. End with one simple question that is easy to answer (e.g. whether they want a short call this week).
Answer with the email body only.
"""

_FORMALITY = {"fr": 'vouvoiement, "vous"', "nl": 'formal "u"',
              "pt": 'portugues de Portugal, formal leve', "en": "polite"}

_FALLBACK = {
    "fr": "Merci pour votre réponse.\n\nJ'ai préparé un premier aperçu pour {name}, avec votre nom{colors}. "
          "Il n'est pas en ligne pour vos clients, c'est juste pour vous le montrer :\n{url}\n\n"
          "{price}Seriez-vous disponible pour un court appel cette semaine ?",
    "nl": "Dank u voor uw reactie.\n\nIk heb een eerste voorbeeld gemaakt voor {name}, met uw naam{colors}. "
          "Het staat niet online voor uw klanten, het is alleen om te laten zien:\n{url}\n\n"
          "{price}Heeft u deze week tijd voor een kort gesprek?",
    "pt": "Obrigado pela resposta.\n\nPreparei uma primeira pré-visualização para a {name}, com o vosso nome{colors}. "
          "Não está online para os clientes, é só para verem:\n{url}\n\n"
          "{price}Teria disponibilidade para uma chamada curta esta semana?",
    "en": "Thanks for getting back to me.\n\nI put together a first preview for {name}, with your name{colors}. "
          "It is not live for your customers, it is just for you to see:\n{url}\n\n"
          "{price}Would you have time for a short call this week?",
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


async def compose_followup(company_name: str, reply_text: str, language: str, url: str,
                           brand_colors: bool, price: str) -> str:
    key = lang_key(language)
    client = LLMClient()
    if client.is_configured:
        system = SYSTEM_PROMPT.format(
            company_name=company_name,
            language_name=LANGUAGE_NAMES.get(key, "English"),
            formality=_FORMALITY.get(key, "polite"),
            url=url,
            colors_clause=" and colours taken from their current website" if brand_colors else "",
            price_rule=f'If they asked about price, say it starts at "{price}".' if price else "Do not mention prices.",
        )
        body = (await client.chat(system, f"Their reply:\n{reply_text[:1500]}", temperature=0.7)).strip()
        if validate_followup(body, url)[0]:
            return body
    return fallback_followup(company_name, language, url, brand_colors, price)
