"""Gera o e-mail frio de abordagem (assunto + corpo) no idioma da empresa.

O alvo e soar como uma pessoa que de fato olhou o site: primeira pessoa do singular, um
problema so, contado do jeito que foi visto, uma frase admitindo que foi visto de fora e
uma pergunta facil no fim. A assinatura e o rodape entram depois (sending/email_body.py).
"""

import json
import re

from app.core.config import settings
from app.core.countries import search_term
from app.i18n import LANGUAGE_NAMES, lang_key
from app.llm.client import LLMClient
from app.llm.sales_agent import _build_context

SYSTEM_PROMPT = """You are {sender}, an independent web developer. You are writing ONE short cold email, as yourself, to the owner of a small local business in Europe. You actually looked at their website and noticed something. Write like a real person writing to another real person: plain, specific, a little humble, never salesy.

HOW IT SHOULD READ:
- First person singular ("je" / "ik" / "eu"). Never "we", "our team", "our agency".
- Start with a simple greeting line, then say plainly how you came across them (you were looking for {term} in {city}).
- Tell ONE concrete thing from the audit data, the way you experienced it ("I opened your site on my phone and..."). One problem only. Never a list.
- If the data says the business has NO website, the problem is that you searched and found none. Never say you opened, visited or tried their site.
- One short sentence admitting you only looked from the outside, so it may already be planned on their side.
- Offer to prepare a preview of a new version with their own name and colours, so they can see it. Say once, simply, that it commits them to nothing. {price_rule}
- End with one short, easy question (e.g. "Shall I send it?").
- Mix short and longer sentences. Natural, everyday words. No exclamation marks.

HARD RULES:
1. Write ONLY in {language_name}, register: {formality}.
2. The exact business name "{company_name}" appears in the body.
3. Every fact must come from the data below. Never invent numbers, reviews, competitors or statistics. If there is no concrete fact to cite, answer exactly: INSUFFICIENT_DATA
4. Body: 60 to 120 words, 3 short paragraphs plus the closing question. Plain text: no links, no emojis, no markdown, no bullet points.
5. Do NOT sign and do NOT add a closing formula (the signature is added automatically).
6. Never use: "I hope this email finds you well", "I am reaching out", "don't hesitate", "online presence", "visibility", "boost", "optimize", "solution", "take your business to the next level", or their equivalents in {language_name}.
7. Subject: 3 to 7 words, all lowercase except names, reads like a note from a person, specific to them. No "!", no clickbait.

EXAMPLE OF THE TONE (illustration only: never copy its facts, names or sentences):
{example}

Answer with a JSON object only: {{"subject": "...", "body": "..."}}
"""

_FORMALITY = {
    "fr": 'vouvoiement ("vous"), chaleureux mais pas familier',
    "nl": 'formeel "u", maar hartelijk',
    "pt": 'portugues de Portugal (nunca brasileiro), formal leve: "o senhor/a senhora" ou "voces"',
    "en": "polite, warm, not stiff",
}

_EXAMPLES = {
    "fr": {"subject": "votre site sur téléphone", "body": (
        "Bonjour,\n\nJe cherchais un barbier dans le 11e et je suis tombé sur Le Comptoir du Barbier. "
        "Sur mon téléphone, le site s'affiche en version ordinateur : il faut zoomer pour trouver les horaires, "
        "et je n'ai pas vu de moyen de réserver.\n\nJe ne l'ai regardé que de l'extérieur, donc c'est peut-être "
        "déjà prévu de votre côté. Sinon, je peux vous préparer un aperçu d'une nouvelle version, avec votre nom "
        "et vos couleurs, pour que vous voyiez à quoi ça ressemblerait. Ça ne vous engage à rien.\n\n"
        "Je vous l'envoie ?")},
    "nl": {"subject": "uw website op mobiel", "body": (
        "Goedendag,\n\nIk zocht een kapper in Rotterdam en kwam Salon De Linde tegen. Op mijn telefoon duurde "
        "het een tijd voordat de site laadde, en een afspraak maken lukte me niet zonder te bellen.\n\n"
        "Ik heb alleen van buitenaf gekeken, dus misschien staat dit al op de planning. Zo niet, dan maak ik "
        "graag een voorbeeld van een nieuwe versie, met uw naam en kleuren, zodat u kunt zien hoe het eruit "
        "zou zien. U zit nergens aan vast.\n\nZal ik het sturen?")},
    "pt": {"subject": "o vosso site no telemóvel", "body": (
        "Bom dia,\n\nEstava à procura de uma barbearia em Lisboa e encontrei a Barbearia do Largo. No "
        "telemóvel, o site abre na versão de computador e não encontrei forma de marcar sem ligar.\n\n"
        "Só vi de fora, por isso pode já estar nos vossos planos. Se não estiver, posso preparar uma "
        "pré-visualização de uma versão nova, com o vosso nome e as vossas cores, para verem como ficaria. "
        "Não fica nenhum compromisso.\n\nQuer que envie?")},
}
_EXAMPLES["en"] = _EXAMPLES["fr"]

_PRICE_RULE = {
    True: 'Mention once, in passing, that a site like this starts at "{price}".',
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


def _sender_first_name() -> str:
    contact = (settings.SENDER_CONTACT_NAME or "").strip()
    return contact.split()[0] if contact else "a freelance web developer"


# O termo de busca do Maps nem sempre serve na frase ("kapper heren" busca bem e le mal).
_PROSE_TERMS = {("barbearia", "nl"): "herenkapper"}


def _category_term(company, language: str) -> str:
    if not company.category:
        return ""
    prose = _PROSE_TERMS.get((company.category.slug, lang_key(language)))
    return prose or search_term(company.category.slug, company.category.name, language)


async def generate_outreach_email(company, audit, opportunities, diagnosis, language: str) -> EmailDraft | None:
    """Retorna None quando nao ha dado concreto para citar (empresa fica sem envio)."""
    key = lang_key(language)
    client = LLMClient()
    if not client.is_configured:
        return fallback_email(company, audit, language)

    price = settings.OFFER_PRICE_RANGE.strip()
    example = _EXAMPLES.get(key, _EXAMPLES["fr"])
    system = SYSTEM_PROMPT.format(
        sender=_sender_first_name(),
        term=_category_term(company, language) or "a business like theirs",
        city=company.city.name if company.city else "their city",
        language_name=LANGUAGE_NAMES.get(key, "English"),
        formality=_FORMALITY.get(key, _FORMALITY["en"]),
        company_name=company.name,
        price_rule=_PRICE_RULE[bool(price)].format(price=price),
        example=json.dumps(example, ensure_ascii=False),
    )
    context = _build_context(company, audit, opportunities, diagnosis)
    user = (
        "Business data (field labels are in Portuguese; the email must be in the target language):\n"
        f"{context}"
    )
    raw = await client.chat(system, user, temperature=0.85)
    return _parse_llm_json(raw)


# --- fallback sem LLM: mesma estrutura dos exemplos, um fato da auditoria por vez ---

_FALLBACK = {
    "fr": {
        "subject": "le site de {name}",
        "mobile": "sur mon téléphone, le site s'affiche en version ordinateur et il faut zoomer pour tout lire",
        "slow": "sur mon téléphone, le site a mis plus de {secs} secondes à s'afficher",
        "booking": "je n'ai pas trouvé de moyen de réserver en ligne sur le site",
        "https": "le navigateur affiche « non sécurisé » en ouvrant le site, faute de HTTPS",
        "body": "Bonjour,\n\nJe cherchais un {category} à {city} et je suis tombé sur {name}. Petite chose que "
                "j'ai remarquée : {fact}.\n\nJe ne l'ai regardé que de l'extérieur, donc c'est peut-être déjà "
                "prévu de votre côté. Sinon, je peux vous préparer un aperçu d'une nouvelle version, avec votre "
                "nom et vos couleurs, pour que vous voyiez à quoi ça ressemblerait.{price} Ça ne vous engage à "
                "rien.\n\nJe vous l'envoie ?",
        "price": " Ce type de site commence à {price}.",
    },
    "nl": {
        "subject": "de website van {name}",
        "mobile": "op mijn telefoon opent de site in de computerversie en moet je inzoomen om iets te lezen",
        "slow": "op mijn telefoon duurde het meer dan {secs} seconden voordat de site verscheen",
        "booking": "ik kon op de site geen manier vinden om online een afspraak te maken",
        "https": "de browser meldt 'niet veilig' bij het openen van de site, omdat HTTPS ontbreekt",
        "body": "Goedendag,\n\nIk zocht een {category} in {city} en kwam {name} tegen. Iets wat me opviel: "
                "{fact}.\n\nIk heb alleen van buitenaf gekeken, dus misschien staat dit al op de planning. "
                "Zo niet, dan maak ik graag een voorbeeld van een nieuwe versie, met uw naam en kleuren, zodat u "
                "kunt zien hoe het eruit zou zien.{price} U zit nergens aan vast.\n\nZal ik het sturen?",
        "price": " Zo'n website begint bij {price}.",
    },
    "pt": {
        "subject": "o site da {name}",
        "mobile": "no telemóvel, o site abre na versão de computador e é preciso fazer zoom para ler",
        "slow": "no telemóvel, o site demorou mais de {secs} segundos a abrir",
        "booking": "não encontrei forma de marcar online no site",
        "https": "o browser mostra 'não seguro' ao abrir o site, por falta de HTTPS",
        "body": "Bom dia,\n\nEstava à procura de {category} em {city} e encontrei a {name}. Uma coisa que "
                "reparei: {fact}.\n\nSó vi de fora, por isso pode já estar nos vossos planos. Se não estiver, "
                "posso preparar uma pré-visualização de uma versão nova, com o vosso nome e as vossas cores, para "
                "verem como ficaria.{price} Não fica nenhum compromisso.\n\nQuer que envie?",
        "price": " Um site assim começa em {price}.",
    },
}


def fallback_email(company, audit, language: str) -> EmailDraft | None:
    texts = _FALLBACK.get(lang_key(language))
    if not texts or not audit:
        return None
    if audit.has_viewport is False:
        fact = texts["mobile"]
    elif audit.response_time_ms and audit.response_time_ms >= 4000:
        fact = texts["slow"].format(secs=audit.response_time_ms // 1000)
    elif audit.has_scheduling is False:
        fact = texts["booking"]
    elif audit.has_https is False:
        fact = texts["https"]
    else:
        return None
    price = settings.OFFER_PRICE_RANGE.strip()
    body = texts["body"].format(
        category=_category_term(company, language),
        city=company.city.name if company.city else "",
        name=company.name,
        fact=fact,
        price=texts["price"].format(price=price) if price else "",
    )
    return EmailDraft(texts["subject"].format(name=company.name), body)
