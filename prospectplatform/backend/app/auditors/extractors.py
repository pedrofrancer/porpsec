"""Funcoes puras de extracao usadas pelo WebsiteAuditor (testaveis sem browser)."""

import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")

_OBFUSCATIONS = [
    (re.compile(r"\s*[\[\(\{]\s*(?:at|arobase|apenstaartje)\s*[\]\)\}]\s*", re.I), "@"),
    (re.compile(r"\s*[\[\(\{]\s*(?:dot|point|punt|ponto)\s*[\]\)\}]\s*", re.I), "."),
]

_IGNORED_DOMAINS = {"example.com", "example.org", "domain.com", "email.com", "yourdomain.com", "mysite.com",
                    "sentry.io", "sentry.wixpress.com", "sentry-next.wixpress.com", "wixpress.com", "wix.com",
                    "godaddy.com", "squarespace.com"}
_IGNORED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")

WEBMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.fr", "hotmail.be", "outlook.com", "outlook.fr",
    "outlook.pt", "live.com", "live.fr", "live.nl", "msn.com", "yahoo.com", "yahoo.fr", "icloud.com", "me.com",
    "aol.com", "sapo.pt", "gmx.com", "gmx.fr", "gmx.net", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr",
    "laposte.net", "skynet.be", "telenet.be", "proximus.be", "ziggo.nl", "kpnmail.nl", "planet.nl", "home.nl",
    "protonmail.com", "proton.me",
}

GENERIC_LOCAL_PARTS = {
    "info", "contact", "contato", "contacto", "geral", "hello", "hallo", "bonjour",
    "reservas", "reservations", "reservation", "reserveringen", "booking", "bookings",
    "office", "mail", "admin", "welcome", "accueil", "secretariat", "secretariaat",
    "rendezvous", "rdv", "afspraak", "afspraken", "marcacoes", "clinica", "salon",
    "salao", "kapsalon", "shop", "atelier", "studio", "team", "equipe", "equipa",
}

# Sinais de pessoa juridica no rodape/texto do site. Ordem importa: mais especifico primeiro.
_LEGAL_FORMS = [
    ("B.V.", re.compile(r"\bB\.\s?V\.(?=\W|$)|\b[A-Z][\w&'-]*\s+BV\b")),
    ("N.V.", re.compile(r"\bN\.\s?V\.(?=\W|$)|\b[A-Z][\w&'-]*\s+NV\b")),
    ("SASU", re.compile(r"\bSASU\b")),
    ("SAS", re.compile(r"\bSAS\b")),
    ("SARL", re.compile(r"\bS\.?A\.?R\.?L\.?(?=\W|$)")),
    ("EURL", re.compile(r"\bEURL\b")),
    ("SRL", re.compile(r"\bSRL\b")),
    ("SPRL", re.compile(r"\bSPRL\b")),
    ("Lda", re.compile(r"\bLda\.?(?=\W|$)|\bLimitada\b")),
    ("S.A.", re.compile(r"\bS\.A\.(?=\W|$)|\bSA\b(?=\s*[,.\-]|\s+au\s+capital)")),
]

# Formas que valem como "rechtspersoon" para a Holanda.
NL_LEGAL_ENTITIES = {"B.V.", "N.V."}

_NAMED_COLORS_TO_SKIP = {"transparent", "inherit", "initial", "currentcolor", "none"}


def _deobfuscate(text: str) -> str:
    for pattern, repl in _OBFUSCATIONS:
        text = pattern.sub(repl, text)
    return text


def extract_emails(*chunks: str) -> list[str]:
    """Extrai e-mails de HTML/texto (inclui mailto: e formas '[at]'). Ordem de aparicao, sem duplicata."""
    found: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        if not chunk:
            continue
        for raw in EMAIL_RE.findall(_deobfuscate(chunk)):
            email = raw.strip(".").lower()
            domain = email.split("@", 1)[1]
            if domain in _IGNORED_DOMAINS or email.endswith(_IGNORED_EXTENSIONS):
                continue
            if re.search(r"@\d+x\.", email):  # logo@2x.png
                continue
            if email not in seen:
                seen.add(email)
                found.append(email)
    return found


def registrable_domain(url_or_domain: str | None) -> str | None:
    """Dominio registravel simplificado (ultimos 2 rotulos). Suficiente para .pt/.be/.fr/.nl/.com."""
    if not url_or_domain:
        return None
    value = url_or_domain.strip().lower()
    if "@" in value:
        host = value.split("@", 1)[1]
    else:
        if "://" not in value:
            value = "http://" + value
        host = urlparse(value).hostname or ""
    host = host.strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) < 2:
        return None
    if len(parts) >= 3 and parts[-2] in {"com", "co", "org", "net"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_webmail(email: str) -> bool:
    return email.split("@", 1)[-1].lower() in WEBMAIL_DOMAINS


def is_generic_local_part(email: str) -> bool:
    local = email.split("@", 1)[0].lower()
    base = re.split(r"[.\-_+]", local)[0]
    return local in GENERIC_LOCAL_PARTS or base in GENERIC_LOCAL_PARTS


def pick_contact_email(emails: list[str], website: str | None) -> str | None:
    """Melhor e-mail de contato: dominio da empresa e caixa generica ganham."""
    site_domain = registrable_domain(website)
    best, best_score = None, -1
    for email in emails:
        score = 0
        if site_domain and registrable_domain(email) == site_domain:
            score += 10
        if is_generic_local_part(email):
            score += 5
        if is_webmail(email):
            score -= 5
        if score > best_score:
            best, best_score = email, score
    return best


def detect_legal_entity(text: str | None) -> str | None:
    if not text:
        return None
    for label, pattern in _LEGAL_FORMS:
        if pattern.search(text):
            return label
    return None


def normalize_lang(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().replace("_", "-")
    if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z]{2,4})?", value):
        return None
    parts = value.split("-")
    return parts[0].lower() + ("-" + parts[1].upper() if len(parts) > 1 else "")


def css_color_to_hex(value: str | None) -> str | None:
    """Converte 'rgb(1, 2, 3)' / 'rgba(...)' / '#abc' para '#rrggbb'. Transparente vira None."""
    if not value:
        return None
    value = value.strip().lower()
    if value in _NAMED_COLORS_TO_SKIP:
        return None
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", value)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return "#" + h
    m = re.fullmatch(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+%?))?\s*\)", value)
    if m:
        alpha = m.group(4)
        if alpha is not None:
            a = float(alpha.rstrip("%")) / (100 if alpha.endswith("%") else 1)
            if a < 0.5:
                return None
        r, g, b = (min(255, int(x)) for x in m.group(1, 2, 3))
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _is_neutral(hex_color: str) -> bool:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    spread = max(r, g, b) - min(r, g, b)
    return spread < 18  # branco, preto e cinzas


def pick_brand_colors(css_colors: list[str], limit: int = 3) -> list[str]:
    """Cores de marca: ignora neutras, ordena por frequencia."""
    counts: dict[str, int] = {}
    for raw in css_colors:
        hex_color = css_color_to_hex(raw)
        if not hex_color or _is_neutral(hex_color):
            continue
        counts[hex_color] = counts.get(hex_color, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [c for c, _ in ranked[:limit]]


def clean_about_snippet(text: str | None, max_len: int = 320) -> str | None:
    """Primeiras frases de um texto 'sobre', sem espacos sobrando."""
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 40:
        return None
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 80 else cut.rsplit(" ", 1)[0] + "..."
