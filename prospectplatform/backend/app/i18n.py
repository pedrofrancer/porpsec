"""Textos fixos por idioma (rodape legal, opt-out). Chave = prefixo do idioma."""

import re

LANGUAGE_NAMES = {
    "pt": "portugues europeu (Portugal)",
    "fr": "francais",
    "nl": "Nederlands",
    "en": "English",
    "es": "espanol",
}

# Palavras que, numa resposta, valem como pedido de descadastro.
OPT_OUT_KEYWORDS = [
    "stop", "unsubscribe", "remove me", "remover", "retirar", "nao quero", "não quero",
    "desinscrire", "désinscrire", "désabonner", "desabonner", "ne plus recevoir",
    "afmelden", "uitschrijven", "geen interesse meer", "niet meer mailen",
]

_FOOTER = {
    "pt": (
        "--\n{brand}{contact_line}\n{address}\n"
        "Recebeu este e-mail porque o contacto de {company} está publicado no site da empresa. "
        "Para não receber mais mensagens, responda STOP e eu removo o endereço de imediato."
    ),
    "fr": (
        "--\n{brand}{contact_line}\n{address}\n"
        "Vous recevez ce message car l'adresse {de_company} est publiée sur son site. "
        "Pour ne plus recevoir de messages, répondez STOP et je supprime l'adresse tout de suite."
    ),
    "nl": (
        "--\n{brand}{contact_line}\n{address}\n"
        "U ontvangt deze e-mail omdat het adres van {company} op de eigen website staat. "
        "Wilt u geen berichten meer? Antwoord STOP en ik verwijder het adres direct."
    ),
    "en": (
        "--\n{brand}{contact_line}\n{address}\n"
        "You are receiving this because the address of {company} is published on its website. "
        "Reply STOP and I will remove the address right away."
    ),
}


def lang_key(language: str | None) -> str:
    prefix = (language or "en").split("-")[0].lower()
    return prefix if prefix in _FOOTER else "en"


def legal_footer(language: str | None, brand: str, address: str, company_name: str,
                 contact_name: str = "", website: str = "") -> str:
    extras = " - ".join(x for x in (contact_name, website) if x)
    contact_line = f" ({extras})" if extras else ""
    return _FOOTER[lang_key(language)].format(
        brand=brand, contact_line=contact_line, address=address, company=company_name,
        de_company=_de(company_name),
    )


def _de(name: str) -> str:
    """Elisao do frances: "d'Atelier", "de Barbier"."""
    first = name.strip()[:1].lower()
    return f"d'{name}" if first and first in "aeiouhàâéèêëîïôûü" else f"de {name}"


def is_opt_out_reply(text: str | None) -> bool:
    if not text:
        return False
    first_lines = "\n".join(text.strip().splitlines()[:5]).lower()
    return any(re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", first_lines) for kw in OPT_OUT_KEYWORDS)
