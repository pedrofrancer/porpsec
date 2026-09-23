"""Parse de e-mail recebido: cabecalhos de thread, texto da resposta sem citacao, bounces."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.utils import getaddresses, parsedate_to_datetime

MSGID_RE = re.compile(r"<[^<>\s]+>")

# Linha que abre a citacao da mensagem original, por idioma.
_QUOTE_HEADERS = re.compile(
    r"^\s*(On .{5,200} wrote:|Le .{5,200} a [ée]crit ?:|Op .{5,200} schreef .{0,80}:|"
    r"Em .{5,200} escreveu:|El .{5,200} escribi[óo]:|-{2,}\s*(Original Message|Message d'origine|"
    r"Oorspronkelijk bericht|Mensagem original)\s*-{2,}|From: .+|De ?: .+|Van: .+)\s*$",
    re.IGNORECASE,
)

_BOUNCE_SENDERS = ("mailer-daemon@", "postmaster@")


@dataclass
class ParsedEmail:
    message_id: str | None
    in_reply_to: list[str]
    references: list[str]
    from_address: str | None
    subject: str
    received_at: datetime
    text: str
    is_bounce: bool = False
    mentioned_ids: list[str] = field(default_factory=list)  # Message-IDs citados no corpo (bounces)

    @property
    def thread_ids(self) -> list[str]:
        """Candidatos a Message-ID do nosso outreach, do mais para o menos confiavel."""
        seen, out = set(), []
        for mid in self.in_reply_to + list(reversed(self.references)) + self.mentioned_ids:
            if mid not in seen:
                seen.add(mid)
                out.append(mid)
        return out


def _ids(value: str | None) -> list[str]:
    return MSGID_RE.findall(value or "")


def _plain_text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError):
        content = part.get_payload(decode=True).decode("utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        content = re.sub(r"<(br|/p|/div)[^>]*>", "\n", content, flags=re.I)
        content = re.sub(r"<[^>]+>", "", content)
    return content


def strip_quoted(text: str) -> str:
    """Mantem so o que a pessoa escreveu: corta na primeira linha de citacao."""
    kept = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith(">") or _QUOTE_HEADERS.match(line):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def parse_email(raw: bytes) -> ParsedEmail:
    msg = message_from_bytes(raw, policy=policy.default)
    addresses = getaddresses([str(msg.get("From", ""))])
    from_address = addresses[0][1].lower() if addresses and addresses[0][1] else None

    try:
        received_at = parsedate_to_datetime(str(msg.get("Date")))
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        received_at = datetime.now(timezone.utc)

    full_text = _plain_text(msg)
    is_bounce = bool(from_address and from_address.startswith(_BOUNCE_SENDERS)) or \
        msg.get_content_type() == "multipart/report"

    mentioned = []
    if is_bounce:
        # O DSN anexa os cabecalhos da mensagem original: o Message-ID dela aparece no corpo bruto.
        mentioned = _ids(raw.decode("utf-8", errors="replace"))

    return ParsedEmail(
        message_id=(_ids(str(msg.get("Message-ID", ""))) or [None])[0],
        in_reply_to=_ids(str(msg.get("In-Reply-To", ""))),
        references=_ids(str(msg.get("References", ""))),
        from_address=from_address,
        subject=str(msg.get("Subject", "")),
        received_at=received_at,
        text=full_text if is_bounce else strip_quoted(full_text),
        is_bounce=is_bounce,
        mentioned_ids=mentioned,
    )
