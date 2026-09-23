import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.inbound.email_parser import parse_email, strip_quoted
from app.inbound.imap_listener import ImapReplyListener
from app.inbound.reply_handler import ReplyEventHandler
from app.models.base import Base
from app.models.category import Category
from app.models.company import Company
from app.models.geography import City, Country, State
from app.models.inbound import InboundReply
from app.models.message import Message
from app.models.prospection import OptOut, ProspectingQueue

OUTREACH_ID = "<outreach-1@gmail.com>"


def raw_email(body, *, sender="contact@barbier-lumiere.fr", subject="Re: le site de Barbier Lumière",
              msgid="<r1@barbier-lumiere.fr>", in_reply_to=OUTREACH_ID, references=None, ctype=None) -> bytes:
    m = EmailMessage()
    m["From"] = f"Barbier Lumière <{sender}>"
    m["To"] = "studio@gmail.com"
    m["Subject"] = subject
    m["Date"] = "Tue, 22 Sep 2026 10:15:00 +0200"
    if msgid:
        m["Message-ID"] = msgid
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
    if references:
        m["References"] = references
    m.set_content(body)
    return bytes(m)


# --- parser ---

def test_strip_quoted_french_client():
    text = "Oui, montrez-moi.\nMerci\n\nLe mar. 22 sept. 2026 à 09:00, Studio <s@gmail.com> a écrit :\n> Bonjour"
    assert strip_quoted(text) == "Oui, montrez-moi.\nMerci"


def test_strip_quoted_dutch_and_gt():
    assert strip_quoted("Graag!\nOp di 22 sep. 2026 schreef Studio <s@gmail.com>:\n> x") == "Graag!"
    assert strip_quoted("Sim\n> citado") == "Sim"


def test_parse_reply_headers_and_text():
    parsed = parse_email(raw_email("Quanto custa?\n\nEm ter., 22/09/2026 escreveu:\n> ola",
                                   references="<a@x> " + OUTREACH_ID))
    assert parsed.message_id == "<r1@barbier-lumiere.fr>"
    assert parsed.from_address == "contact@barbier-lumiere.fr"
    assert parsed.text == "Quanto custa?"
    assert parsed.thread_ids[0] == OUTREACH_ID
    assert parsed.received_at.tzinfo is not None
    assert not parsed.is_bounce


def test_parse_bounce_finds_original_id():
    body = f"Delivery to the following recipient failed permanently.\n\nMessage-ID: {OUTREACH_ID}\n"
    parsed = parse_email(raw_email(body, sender="mailer-daemon@googlemail.com", in_reply_to=None,
                                   subject="Delivery Status Notification (Failure)", msgid="<b1@google>"))
    assert parsed.is_bounce
    assert OUTREACH_ID in parsed.thread_ids
