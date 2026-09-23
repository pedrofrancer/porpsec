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


# --- handler ---

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add_all([Country(id=1, name="France", code="FR"), State(id=1, name="IDF", code="FR-IDF", country_id=1),
               City(id=1, name="Paris", state_id=1), Category(id=1, name="Barbearia", slug="barbearia")])
    s.commit()
    yield s
    s.close()


@pytest.fixture
def sent(db):
    c = Company(name="Barbier Lumière", city_id=1, category_id=1, website="https://barbier-lumiere.fr",
                email="contact@barbier-lumiere.fr", preferred_channel="email", source="test",
                collected_at=datetime.now(timezone.utc))
    db.add(c)
    db.commit()
    m = Message(company_id=c.id, opportunity_ids="[]", message_text="corpo", channel="email", subject="le site",
                status="enviado", thread_id=OUTREACH_ID, generated_at=datetime.now(timezone.utc),
                sent_at=datetime.now(timezone.utc))
    db.add_all([m, ProspectingQueue(company_id=c.id, status="ENVIADO")])
    db.commit()
    return c, m


def test_first_reply_marks_queue_and_calls_hook(db, sent):
    company, outreach = sent
    hook = MagicMock()
    reply = ReplyEventHandler(db, on_first_reply=hook).handle(parse_email(raw_email("Oui, pourquoi pas")))
    assert reply.kind == "reply" and reply.is_first_reply and reply.message_id == outreach.id
    assert db.query(ProspectingQueue).one().status == "RESPONDEU"
    hook.assert_called_once()
    assert hook.call_args.args[1].id == company.id


def test_same_email_twice_is_idempotent(db, sent):
    handler = ReplyEventHandler(db)
    raw = raw_email("Oui")
    assert handler.handle(parse_email(raw)) is not None
    assert handler.handle(parse_email(raw)) is None
    assert db.query(InboundReply).count() == 1


def test_second_reply_is_not_first(db, sent):
    hook = MagicMock()
    handler = ReplyEventHandler(db, on_first_reply=hook)
    handler.handle(parse_email(raw_email("Oui")))
    second = handler.handle(parse_email(raw_email("Et le prix ?", msgid="<r2@barbier-lumiere.fr>")))
    assert second.kind == "reply" and not second.is_first_reply
    hook.assert_called_once()


def test_stop_reply_registers_opt_out(db, sent):
    hook = MagicMock()
    reply = ReplyEventHandler(db, on_first_reply=hook).handle(parse_email(raw_email("STOP merci")))
    assert reply.kind == "opt_out"
    assert db.query(OptOut).filter_by(contact_identifier="contact@barbier-lumiere.fr").one()
    assert db.query(ProspectingQueue).one().status == "BLOQUEADO_OPT_OUT"
    hook.assert_not_called()


def test_list_unsubscribe_mail_without_thread_headers(db, sent):
    raw = raw_email("", subject="STOP", in_reply_to=None, msgid="<u1@barbier-lumiere.fr>")
    reply = ReplyEventHandler(db).handle(parse_email(raw))
    assert reply.kind == "opt_out"


def test_reply_from_colleague_same_domain_without_headers(db, sent):
    raw = raw_email("Je transmets à la gérante", sender="marie@barbier-lumiere.fr", in_reply_to=None,
                    msgid="<c1@barbier-lumiere.fr>")
    assert ReplyEventHandler(db).handle(parse_email(raw)).kind == "reply"


def test_bounce_marks_message(db, sent):
    _, outreach = sent
    body = f"Address not found\nMessage-ID: {OUTREACH_ID}"
    raw = raw_email(body, sender="mailer-daemon@googlemail.com", in_reply_to=None, msgid="<b1@google>")
    reply = ReplyEventHandler(db).handle(parse_email(raw))
    assert reply.kind == "bounce"
    db.refresh(outreach)
    assert outreach.status == "bounce"


def test_unrelated_email_is_ignored(db, sent):
    raw = raw_email("Newsletter", sender="news@shop.com", in_reply_to=None, msgid="<n1@shop.com>")
    assert ReplyEventHandler(db).handle(parse_email(raw)) is None
    assert db.query(InboundReply).count() == 0


def test_hook_failure_does_not_lose_reply(db, sent):
    handler = ReplyEventHandler(db, on_first_reply=MagicMock(side_effect=RuntimeError("boom")))
    assert handler.handle(parse_email(raw_email("Oui"))) is not None
    assert db.query(InboundReply).count() == 1


# --- listener (IMAP falso) ---

def test_poll_once_downloads_only_new(db, sent):
    known = raw_email("Oui", msgid="<r1@barbier-lumiere.fr>")
    new = raw_email("Et le prix ?", msgid="<r2@barbier-lumiere.fr>")
    boxes = {b"1": known, b"2": new}
    ReplyEventHandler(db).handle(parse_email(known))

    imap = MagicMock()
    imap.__enter__.return_value = imap
    imap.search.return_value = ("OK", [b"1 2"])

    def fetch(num, what):
        raw = boxes[num]
        if "HEADER.FIELDS" in what:
            mid = parse_email(raw).message_id
            return "OK", [(b"hdr", f"Message-ID: {mid}\r\n".encode())]
        return "OK", [(b"body", raw)]

    imap.fetch.side_effect = fetch
    listener = ImapReplyListener(lambda: (ReplyEventHandler(db), db_proxy(db)))
    with patch("app.inbound.imap_listener.imaplib.IMAP4_SSL", return_value=imap), \
         patch("app.inbound.imap_listener.settings") as s:
        s.EMAIL_ADDRESS, s.EMAIL_APP_PASSWORD = "studio@gmail.com", "x"
        assert listener.poll_once() == 1

    body_fetches = [c for c in imap.fetch.call_args_list if "HEADER.FIELDS" not in c.args[1]]
    assert [c.args[0] for c in body_fetches] == [b"2"]
    assert db.query(InboundReply).count() == 2


def db_proxy(db):
    """Sessao real, mas close() nao fecha (o teste continua usando)."""
    proxy = MagicMock(wraps=db)
    proxy.query = db.query
    proxy.close = MagicMock()
    return proxy
