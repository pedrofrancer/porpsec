import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.branding.brand_kit import Photo, build_brand_kit
from app.branding.preview_service import PreviewError, PreviewService, enqueue_for_reply
from app.branding.publisher import PagesPublisher, PublishError, make_slug
from app.branding.site_renderer import contrast_ratio, readable_on, render_site
from app.llm.followup_agent import fallback_followup, validate_followup
from app.models.audit import Audit
from app.models.base import Base
from app.models.category import Category
from app.models.company import Company
from app.models.geography import City, Country, State
from app.models.inbound import InboundReply
from app.models.message import Message
from app.models.preview import SitePreview
from app.models.prospection import OptOut, ProspectingQueue

URL = "https://studio-previas.pages.dev/p/barbier-lumiere-abc123/"


def ns_company(**kw):
    base = dict(name="Barbier Lumière", category=SimpleNamespace(slug="barbearia", name="Barbearia"),
                city=SimpleNamespace(name="Paris"), address="12 Rue de Charonne", phone="+33 1 23",
                email="contact@barbier-lumiere.fr", website="https://barbier-lumiere.fr", instagram=None,
                google_rating=4.7, google_review_count=182)
    base.update(kw)
    return SimpleNamespace(**base)


def ns_audit(**kw):
    base = dict(dominant_colors=None, og_image_url=None, logo_url=None, about_snippet=None, site_lang="fr")
    base.update(kw)
    return SimpleNamespace(**base)


# --- brand kit ---

def test_brand_kit_uses_site_colors_logo_and_own_photo():
    audit = ns_audit(dominant_colors=json.dumps(["#e0b050", "#223344"]), og_image_url="https://x.fr/hero.jpg",
                     logo_url="https://x.fr/logo.png", about_snippet="Depuis 2010 rue de Charonne.")
    kit = build_brand_kit(ns_company(), audit, "fr-FR", photo_source=lambda q, n: [])
    assert kit.primary == "#e0b050" and kit.accent == "#223344" and kit.brand_colors_from_site
    assert kit.hero.url == "https://x.fr/hero.jpg" and kit.hero.credit is None
    assert kit.logo_url == "https://x.fr/logo.png"
    assert kit.category_label == "barbier" and kit.mood == "bold"
    assert not kit.stock_photos


def test_brand_kit_stock_photos_are_flagged():
    photos = [Photo(f"https://images.pexels.com/{i}.jpg", "Ana / Pexels") for i in range(4)]
    kit = build_brand_kit(ns_company(), ns_audit(), "fr-FR", photo_source=lambda q, n: photos[:n])
    assert kit.stock_photos and kit.hero.credit == "Ana / Pexels" and len(kit.gallery) == 3
    assert not kit.brand_colors_from_site


def test_brand_kit_without_photos_or_colors():
    kit = build_brand_kit(ns_company(category=SimpleNamespace(slug="clinica", name="Clínica")), ns_audit(),
                          "nl-NL", photo_source=lambda q, n: [])
    assert kit.hero is None and kit.gallery == [] and kit.mood == "soft"
    assert kit.category_label == "schoonheidssalon"


# --- renderer ---

def test_readable_on_picks_best_contrast():
    assert readable_on("#c8a45a") == "#111111"
    assert readable_on("#1f3a5f") == "#ffffff"
    assert contrast_ratio("#ffffff", "#000000") > 20


def test_render_site_localized_and_safe():
    kit = build_brand_kit(ns_company(name="Chez <Léo>"), ns_audit(), "fr-FR", photo_source=lambda q, n: [])
    html = render_site(kit, "Studio Nord")
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert "Chez &lt;Léo&gt;" in html and "Chez <Léo>" not in html
    assert "Aperçu réalisé par Studio Nord" in html
    assert "Réserver un créneau" in html and "4,7 sur Google · 182 avis" in html
    assert "Photos d'illustration" not in html  # sem foto de banco, sem rodape de credito


def test_render_site_stock_note_with_credit():
    photos = [Photo(f"https://images.pexels.com/{i}.jpg", "Ana / Pexels") for i in range(4)]
    kit = build_brand_kit(ns_company(), ns_audit(), "pt-PT", photo_source=lambda q, n: photos[:n])
    html = render_site(kit, "Studio Nord")
    assert "Fotografias ilustrativas (Ana / Pexels)" in html
    assert 'lang="pt-PT"' in html


# --- publisher ---

def test_make_slug():
    slug = make_slug("Barbier Lumière & Fils")
    assert slug.startswith("barbier-lumiere-fils-") and len(slug.split("-")[-1]) == 6


def test_publisher_writes_and_removes(tmp_path):
    pub = PagesPublisher(root=tmp_path)
    pub.write("abc", "<html></html>")
    assert (tmp_path / "p" / "abc" / "index.html").exists()
    assert "Disallow: /" in (tmp_path / "robots.txt").read_text()
    assert "noindex" in (tmp_path / "_headers").read_text()
    pub.remove(["abc"])
    assert not (tmp_path / "p" / "abc").exists()


def test_publisher_deploy_calls_wrangler(tmp_path):
    runner = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    with patch("app.branding.publisher.settings") as s, patch("app.branding.publisher.shutil.which", return_value="npx"):
        s.pages_configured = True
        s.CLOUDFLARE_PAGES_PROJECT, s.CLOUDFLARE_API_TOKEN, s.CLOUDFLARE_ACCOUNT_ID = "studio", "tok", "acc"
        PagesPublisher(root=tmp_path, runner=runner).deploy()
    deploy_args = runner.call_args_list[-1].args[0]
    assert deploy_args[:5] == ["npx", "--yes", "wrangler", "pages", "deploy"]
    assert "--project-name" in deploy_args and "studio" in deploy_args
    assert runner.call_args_list[-1].kwargs["env"]["CLOUDFLARE_API_TOKEN"] == "tok"


def test_publisher_not_configured(tmp_path):
    with patch("app.branding.publisher.settings") as s:
        s.pages_configured = False
        with pytest.raises(PublishError):
            PagesPublisher(root=tmp_path).deploy()


# --- follow-up ---

def test_fallback_followup_has_link_and_price():
    text = fallback_followup("Barbier Lumière", "fr-FR", URL, True, "490 €")
    assert URL in text and "vos couleurs" in text and "490 €" in text
    assert validate_followup(text, URL) == (True, None)


@pytest.mark.parametrize("body,err", [
    ("Merci, voici tout.", "sem o link"),
    (f"Voici {URL} et aussi https://autre.fr", "link que nao"),
    (f"J'espère que vous allez bien. {URL}", "automatico"),
])
def test_validate_followup_rejects(body, err):
    ok, error = validate_followup(body, URL)
    assert not ok and err in error


# --- servico (banco em memoria) ---

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
def replied(db):
    c = Company(name="Barbier Lumière", city_id=1, category_id=1, website="https://barbier-lumiere.fr",
                email="contact@barbier-lumiere.fr", preferred_channel="email", source="test",
                collected_at=datetime.now(timezone.utc))
    db.add(c)
    db.commit()
    db.add(Audit(company_id=c.id, digital_score=30, site_lang="fr", audited_at=datetime.now(timezone.utc)))
    out = Message(company_id=c.id, opportunity_ids="[]", message_text="x", channel="email", subject="le site",
                  language="fr-FR", status="enviado", thread_id="<out@gmail.com>",
                  generated_at=datetime.now(timezone.utc), sent_at=datetime.now(timezone.utc))
    db.add_all([out, ProspectingQueue(company_id=c.id, status="RESPONDEU")])
    db.commit()
    reply = InboundReply(company_id=c.id, message_id=out.id, channel="email", external_id="<r1@barbier-lumiere.fr>",
                         from_address="contact@barbier-lumiere.fr", raw_content="C'est combien ?", kind="reply",
                         is_first_reply=True, received_at=datetime.now(timezone.utc))
    db.add(reply)
    db.commit()
    return c, out, reply


@pytest.fixture
def fakes(tmp_path):
    publisher = PagesPublisher(root=tmp_path)
    publisher.deploy = MagicMock(return_value="ok")
    publisher.public_url = lambda slug: f"https://studio.pages.dev/p/{slug}/"
    sender = SimpleNamespace(is_configured=AsyncMock(return_value=True),
                             send=AsyncMock(return_value={"message_id": "<fu@gmail.com>"}))
    return publisher, sender


@pytest.fixture
def offline():
    with patch("app.branding.brand_kit.pexels_photos", return_value=[]), \
         patch("app.llm.followup_agent.LLMClient") as llm:
        llm.return_value.is_configured = False
        yield


def test_enqueue_is_once_per_company(db, replied):
    company, out, reply = replied
    assert enqueue_for_reply(db, reply, company, out) is not None
    assert enqueue_for_reply(db, reply, company, out) is None
    assert db.query(SitePreview).count() == 1


@pytest.mark.asyncio
async def test_draft_then_approve_sends_in_thread(db, replied, fakes, offline):
    company, out, reply = replied
    publisher, sender = fakes
    preview = enqueue_for_reply(db, reply, company, out)
    service = PreviewService(db, publisher=publisher, sender=sender)

    await service.process_pending()
    assert preview.status == "rascunho"
    assert preview.followup_subject == "Re: le site"
    assert preview.preview_url in preview.followup_text
    assert (publisher.page_dir(preview.slug) / "index.html").exists()
    publisher.deploy.assert_not_called()   # rascunho nao publica
    sender.send.assert_not_called()

    await service.approve(preview)
    publisher.deploy.assert_called_once()
    to, subject, body = sender.send.call_args.args
    assert to == "contact@barbier-lumiere.fr" and subject == "Re: le site"
    assert sender.send.call_args.kwargs == {"in_reply_to": "<r1@barbier-lumiere.fr>", "references": "<out@gmail.com>"}
    assert "STOP" in body
    assert preview.status == "enviado" and preview.expires_at is not None
    fu = db.get(Message, preview.followup_message_id)
    assert fu.message_type == "template_followup" and fu.thread_id == "<fu@gmail.com>"
    assert db.query(ProspectingQueue).one().status == "PREVIA_ENVIADA"
    db.refresh(reply)
    assert reply.resulted_in_template


@pytest.mark.asyncio
async def test_auto_send_flag(db, replied, fakes, offline):
    company, out, reply = replied
    publisher, sender = fakes
    preview = enqueue_for_reply(db, reply, company, out)
    with patch("app.branding.preview_service.settings") as s:
        s.PREVIEW_AUTO_SEND, s.PREVIEW_TTL_DAYS = True, 30
        s.SENDER_BRAND = s.SENDER_POSTAL_ADDRESS = s.SENDER_CONTACT_NAME = s.SENDER_WEBSITE = ""
        s.OFFER_PRICE_RANGE, s.LLM_MODEL = "", "x"
        await PreviewService(db, publisher=publisher, sender=sender).process_pending()
    assert preview.status == "enviado"


@pytest.mark.asyncio
async def test_approve_blocked_by_opt_out(db, replied, fakes, offline):
    company, out, reply = replied
    publisher, sender = fakes
    preview = enqueue_for_reply(db, reply, company, out)
    service = PreviewService(db, publisher=publisher, sender=sender)
    await service.build_draft(preview)
    db.add(OptOut(contact_identifier="contact@barbier-lumiere.fr"))
    db.commit()
    with pytest.raises(PreviewError, match="opt-out"):
        await service.approve(preview)
    sender.send.assert_not_called()


@pytest.mark.asyncio
async def test_approve_rejects_edit_without_link(db, replied, fakes, offline):
    company, out, reply = replied
    publisher, sender = fakes
    preview = enqueue_for_reply(db, reply, company, out)
    service = PreviewService(db, publisher=publisher, sender=sender)
    await service.build_draft(preview)
    with pytest.raises(PreviewError, match="link"):
        await service.approve(preview, text="Bonjour, voici le site.")


def test_expire_old_removes_folder(db, replied, fakes):
    company, out, reply = replied
    publisher, _ = fakes
    preview = SitePreview(company_id=company.id, slug="old-1", status="enviado",
                          expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    db.add(preview)
    db.commit()
    publisher.write("old-1", "<html></html>")
    with patch("app.branding.publisher.settings") as s:
        s.pages_configured = True
        assert PreviewService(db, publisher=publisher).expire_old() == 1
    assert preview.status == "expirado" and not publisher.page_dir("old-1").exists()
    publisher.deploy.assert_called_once()
