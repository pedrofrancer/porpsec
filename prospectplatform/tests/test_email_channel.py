import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.countries import get_country
from app.i18n import is_opt_out_reply, legal_footer
from app.llm.email_agent import _parse_llm_json, fallback_email
from app.models.audit import Audit
from app.models.base import Base
from app.models.category import Category
from app.models.company import Company
from app.models.geography import City, Country, State
from app.models.message import Message
from app.models.prospection import ActionLog, OptOut, ProspectingQueue
from app.prospecting.channel_router import decide_channel, resolve_channel
from app.prospecting.email_policy import check_email_eligibility
from app.sending.dispatcher import Dispatcher, WarmupManager
from app.sending.email_client import EmailSender
from app.sending.email_validator import validate_email

FR = get_country("FR")
NL = get_country("NL")
ES = get_country("ES")
BR = get_country("BR")

GOOD_BODY = (
    "Bonjour,\n\nEn cherchant un barbier à Paris, je suis tombé sur Barbier Lumière : votre site "
    "s'affiche mal sur téléphone et on ne peut pas réserver en ligne. Beaucoup de clients "
    "abandonnent à ce moment-là, surtout le soir.\n\nJe peux vous envoyer un aperçu de ce que "
    "pourrait être votre nouveau site, avec votre nom, vos couleurs et vos photos. Cela vous intéresse ?"
)


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def company_obj(**kw):
    base = dict(email="contact@barbier-lumiere.fr", website="https://www.barbier-lumiere.fr",
                phone="+33 1 23 45 67 89", preferred_channel=None)
    base.update(kw)
    return Obj(**base)


def audit_obj(**kw):
    base = dict(legal_entity_signal=None, whatsapp_catalog_link=False, whatsapp_responds_badge=False,
                has_viewport=False, response_time_ms=1500, has_scheduling=False, has_https=True, site_lang="fr")
    base.update(kw)
    return Obj(**base)


# --- politica de e-mail ---

def test_policy_accepts_generic_company_mailbox():
    assert check_email_eligibility(company_obj(), audit_obj(), FR) == (True, None)


def test_policy_accepts_brand_mailbox():
    c = company_obj(email="barbierlumiere@barbier-lumiere.fr")
    assert check_email_eligibility(c, audit_obj(), FR)[0]


@pytest.mark.parametrize("email,reason_part", [
    (None, "sem e-mail"),
    ("barbier.lumiere@gmail.com", "webmail"),
    ("contact@autre-domaine.fr", "fora do dominio"),
    ("jean.dupont@barbier-lumiere.fr", "pessoal"),
])
def test_policy_rejects(email, reason_part):
    ok, reason = check_email_eligibility(company_obj(email=email), audit_obj(), FR)
    assert not ok
    assert reason_part in reason


def test_policy_requires_site():
    ok, reason = check_email_eligibility(company_obj(website=None), audit_obj(), FR)
    assert not ok and "sem site" in reason


def test_policy_nl_requires_bv():
    c = company_obj(email="info@kapper.nl", website="https://kapper.nl")
    assert not check_email_eligibility(c, audit_obj(), NL)[0]
    assert check_email_eligibility(c, audit_obj(legal_entity_signal="B.V."), NL)[0]
    assert not check_email_eligibility(c, audit_obj(legal_entity_signal="SARL"), NL)[0]


def test_policy_spain_disabled():
    ok, reason = check_email_eligibility(company_obj(), audit_obj(), ES)
    assert not ok and "desligado" in reason


# --- roteamento de canal ---

def test_router_eu_uses_email_even_with_phone():
    assert decide_channel(company_obj(), audit_obj(whatsapp_responds_badge=True), FR) == ("email", None)


def test_router_eu_without_valid_email_is_not_eligible():
    channel, reason = decide_channel(company_obj(email="x@gmail.com"), audit_obj(), FR)
    assert channel is None and "webmail" in reason


def test_router_brazil_stays_whatsapp():
    assert decide_channel(company_obj(email=None), audit_obj(), BR) == ("whatsapp", None)


def test_resolve_channel_freezes_first_decision():
    c = company_obj()
    assert resolve_channel(c, audit_obj(), FR) == ("email", None)
    assert c.preferred_channel == "email"
    c.email = None  # mesmo perdendo o e-mail depois, o canal nao muda
    assert resolve_channel(c, audit_obj(), FR) == ("email", None)


# --- validacao do e-mail ---

def test_validate_email_ok():
    assert validate_email("le site de barbier lumière", GOOD_BODY, "Barbier Lumière") == (True, None)


@pytest.mark.parametrize("subject,body,err", [
    ("", GOOD_BODY, "Assunto vazio"),
    ("offre incroyable !", GOOD_BODY, "'!'"),
    ("le site", GOOD_BODY + " https://x.fr", "Link"),
    ("le site", GOOD_BODY.replace("Barbier Lumière", "votre salon"), "Nome da empresa"),
    ("le site", GOOD_BODY + " [Nom]", "Placeholder"),
    ("le site", "J'espère que vous allez bien. " + GOOD_BODY, "automatico"),
    ("le site", "Bonjour Barbier Lumière, " + "je voulais vous écrire un petit mot. " * 8, "generico"),
    ("le site", "J'espère que ce message vous trouve bien. " + GOOD_BODY, "automatico"),
])
def test_validate_email_rejects(subject, body, err):
    ok, error = validate_email(subject, body, "Barbier Lumière")
    assert not ok and err in error


# --- i18n ---

def test_legal_footer_languages():
    fr = legal_footer("fr-BE", "Studio Nord", "Rua X 1, Lisboa", "Barbier Lumière", "Pedro", "studionord.pages.dev")
    assert "Studio Nord (Pedro - studionord.pages.dev)" in fr
    assert "STOP" in fr and "Barbier Lumière" in fr
    assert "Antwoord STOP" in legal_footer("nl-NL", "B", "A", "C")
    assert "responda STOP" in legal_footer("pt-PT", "B", "A", "C")


@pytest.mark.parametrize("text,expected", [
    ("STOP", True),
    ("Merci de me désinscrire", True),
    ("Graag afmelden", True),
    ("Oui, envoyez l'aperçu !", False),
    ("nonstop disponible", False),
])
def test_opt_out_reply(text, expected):
    assert is_opt_out_reply(text) is expected


# --- gerador ---

def test_parse_llm_json():
    d = _parse_llm_json('Here: {"subject": "le site", "body": "corps"}')
    assert d.subject == "le site" and d.body == "corps"
    assert _parse_llm_json("INSUFFICIENT_DATA") is None
    assert _parse_llm_json("sem json") is None


def test_fallback_email_uses_local_search_term():
    company = Obj(name="Barbier Lumière", category=Obj(slug="barbearia", name="Barbearia"), city=Obj(name="Paris"))
    draft = fallback_email(company, audit_obj(), "fr-FR")
    assert "barbier à Paris" in draft.body
    assert "téléphone" in draft.body
    assert validate_email(draft.subject, draft.body, "Barbier Lumière") == (True, None)


def test_fallback_email_none_without_fact():
    company = Obj(name="X", category=None, city=None)
    ok_audit = audit_obj(has_viewport=True, has_scheduling=True, has_https=True, response_time_ms=900)
    assert fallback_email(company, ok_audit, "fr-FR") is None


# --- EmailSender ---

def test_build_message_headers():
    with patch("app.sending.email_client.settings") as s:
        s.EMAIL_ADDRESS = "studio@gmail.com"
        s.SENDER_CONTACT_NAME = "Pedro"
        s.SENDER_BRAND = "Studio Nord"
        sender = EmailSender()
        msg = sender.build_message("info@x.fr", "assunto", "corpo", in_reply_to="<a@b>")
    assert msg["From"] == "Pedro <studio@gmail.com>"
    assert msg["Message-ID"].endswith("@gmail.com>")
    assert msg["In-Reply-To"] == "<a@b>"
    assert "mailto:studio@gmail.com?subject=STOP" in msg["List-Unsubscribe"]


# --- dispatcher (banco em memoria, pais FR) ---

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        Country(id=1, name="France", code="FR"),
        State(id=1, name="Ile-de-France", code="FR-IDF", country_id=1),
        City(id=1, name="Paris", state_id=1),
        Category(id=1, name="Barbearia", slug="barbearia"),
    ])
    session.commit()
    yield session
    session.close()


@pytest.fixture
def fr_company(db):
    c = Company(name="Barbier Lumière", city_id=1, category_id=1, website="https://www.barbier-lumiere.fr",
                email="contact@barbier-lumiere.fr", source="test", collected_at=datetime.now(timezone.utc))
    db.add(c)
    db.commit()
    db.add(Audit(company_id=c.id, digital_score=30, has_viewport=False, has_https=True, has_scheduling=False,
                 response_time_ms=1500, site_lang="fr", audited_at=datetime.now(timezone.utc)))
    db.commit()
    return c


@pytest.fixture
def no_llm():
    with patch("app.llm.email_agent.LLMClient") as cls:
        cls.return_value.is_configured = False
        yield


@pytest.mark.asyncio
async def test_auto_enqueue_eu_company_goes_email(db, fr_company, no_llm):
    d = Dispatcher(db)
    assert await d._auto_enqueue() == 1
    db.refresh(fr_company)
    assert fr_company.preferred_channel == "email"
    msg = db.query(Message).filter_by(company_id=fr_company.id).one()
    assert msg.channel == "email" and msg.status == "aprovado" and msg.language == "fr-FR"
    assert msg.subject
    assert "STOP" in msg.message_text  # rodape legal anexado
    assert db.query(ProspectingQueue).filter_by(company_id=fr_company.id).one().status == "PENDENTE"


@pytest.mark.asyncio
async def test_auto_enqueue_marks_not_eligible(db, fr_company, no_llm):
    fr_company.email = "barbier@gmail.com"
    db.commit()
    d = Dispatcher(db)
    await d._auto_enqueue()
    entry = db.query(ProspectingQueue).filter_by(company_id=fr_company.id).one()
    assert entry.status == "NAO_ELEGIVEL" and "webmail" in entry.notes
    assert d._get_eligible_companies() == []  # nao volta para a fila a cada ciclo


@pytest.mark.asyncio
async def test_send_email_records_thread_and_legal_basis(db, fr_company, no_llm):
    d = Dispatcher(db)
    await d._auto_enqueue()
    entry = db.query(ProspectingQueue).filter_by(company_id=fr_company.id).one()

    with patch("app.sending.email_client.EmailSender.is_configured", new=AsyncMock(return_value=True)), \
         patch("app.sending.email_client.EmailSender.send",
               new=AsyncMock(return_value={"message_id": "<abc@gmail.com>", "to": "x"})) as send, \
         patch.object(WarmupManager, "register_first_use"):
        assert await d._process_company(entry) is True

    to, subject, body = send.call_args.args
    assert to == "contact@barbier-lumiere.fr" and subject and "STOP" in body
    msg = db.query(Message).filter_by(company_id=fr_company.id).one()  # reaproveitou a msg aprovada
    assert msg.status == "enviado" and msg.thread_id == "<abc@gmail.com>"
    log = db.query(ActionLog).filter_by(action="mensagem_enviada").one()
    assert "CNIL" in log.details


@pytest.mark.asyncio
async def test_send_email_not_configured_keeps_message(db, fr_company, no_llm):
    d = Dispatcher(db)
    await d._auto_enqueue()
    entry = db.query(ProspectingQueue).filter_by(company_id=fr_company.id).one()
    with patch("app.sending.email_client.EmailSender.is_configured", new=AsyncMock(return_value=False)):
        assert await d._process_company(entry) is False
    msg = db.query(Message).filter_by(company_id=fr_company.id).one()
    assert msg.status == "aprovado"
    assert d._consecutive_errors == 0


def test_email_opt_out_blocks(db, fr_company):
    db.add(OptOut(contact_identifier="contact@barbier-lumiere.fr"))
    db.commit()
    d = Dispatcher(db)
    assert d._check_opt_out(fr_company)
    assert d._get_eligible_companies() == []


def test_send_window_per_country():
    d = Dispatcher(None)
    with patch("app.sending.dispatcher.datetime") as mock_dt:
        # 08:30 UTC = 10:30 em Paris (dentro) e 05:30 em Sao Paulo (fora)
        fixed = datetime(2026, 9, 22, 8, 30, tzinfo=timezone.utc)
        mock_dt.now.side_effect = lambda tz=None: fixed.astimezone(tz) if tz else fixed
        assert d._is_within_send_window(FR)
        assert not d._is_within_send_window(BR)
        assert not d._is_within_send_window()


def test_warmup_is_per_channel(tmp_path):
    original = WarmupManager.WARMUP_FILE
    WarmupManager.WARMUP_FILE = tmp_path / "warmup_state.json"
    try:
        WarmupManager.register_first_use("email")
        assert WarmupManager._file("email").exists()
        assert not WarmupManager.WARMUP_FILE.exists()
        assert WarmupManager.get_max_today("email") == 5
    finally:
        WarmupManager.WARMUP_FILE = original
