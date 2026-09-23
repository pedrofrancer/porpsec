"""Guarda-corpo do e-mail antes do envio (mesma filosofia do ContentValidator do WhatsApp)."""

import re

PLACEHOLDER_PATTERNS = [r"\[[^\]]*\]", r"\{\{.*?\}\}", r"\{[a-z_]+\}", r"TODO", r"PLACEHOLDER", r"INSUFFICIENT_DATA", r"<[a-z]+>"]

# Evidencia concreta citavel, em FR/NL/PT/EN.
SPECIFICITY_KEYWORDS = [
    r"site", r"website", r"web", r"https", r"s[ée]curis", r"veilig", r"seguro",
    r"t[ée]l[ée]phone", r"mobile", r"telefoon", r"telem[óo]vel", r"smartphone",
    r"charg", r"laad", r"carreg", r"lent", r"traag", r"seconde", r"segundo",
    r"r[ée]serv", r"rendez-vous", r"boek", r"afspra", r"reserv", r"marca[çc]", r"agend",
    r"google", r"avis", r"review", r"recensie", r"avalia", r"instagram", r"photo", r"foto",
]

AI_TELLS = [
    r"i hope this (e-?mail|message) finds you", r"j'esp[èe]re que (ce|vous)", r"ik hoop dat deze",
    r"espero que (este|se encontre)", r"\bdelve\b", r"game[- ]changer", r"unlock", r"elevate",
    r"in today's digital", r"à l'[èe]re du num[ée]rique", r"in het digitale tijdperk",
    r"na era digital", r"—",
]

SUBJECT_MAX = 90
BODY_MAX = 1200
BODY_MIN_WORDS = 35


def validate_email(subject: str | None, body: str | None, company_name: str) -> tuple[bool, str | None]:
    if not subject or not subject.strip():
        return False, "Assunto vazio"
    if not body or not body.strip():
        return False, "Corpo vazio"
    if len(subject) > SUBJECT_MAX:
        return False, f"Assunto muito longo ({len(subject)} chars, max {SUBJECT_MAX})"
    if "!" in subject:
        return False, "Assunto com '!'"
    if len(body) > BODY_MAX:
        return False, f"Corpo muito longo ({len(body)} chars, max {BODY_MAX})"
    if len(body.split()) < BODY_MIN_WORDS:
        return False, "Corpo curto demais para ser especifico"

    for text in (subject, body):
        for pattern in PLACEHOLDER_PATTERNS:
            if re.search(pattern, text, 0 if pattern.isupper() else re.IGNORECASE):
                return False, f"Placeholder detectado: {pattern}"

    if re.search(r"https?://|www\.", body, re.IGNORECASE):
        return False, "Link no primeiro e-mail (prejudica entrega; a previa vai so apos resposta)"

    if company_name.lower() not in body.lower():
        return False, f"Nome da empresa '{company_name}' nao encontrado no corpo"

    low = body.lower()
    if not any(re.search(kw, low) for kw in SPECIFICITY_KEYWORDS):
        return False, "E-mail generico: nenhum dado concreto da empresa"

    for tell in AI_TELLS:
        if re.search(tell, low):
            return False, f"Frase com cara de texto automatico: {tell}"

    return True, None
