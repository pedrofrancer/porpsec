import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.branding.brand_kit import BrandKit, category_palette
from app.branding.final_site_service import FinalSiteError, FinalSiteService, missing_for_final
from app.branding.publisher import PagesPublisher
from app.models.audit import Audit
from app.models.base import Base
from app.models.category import Category
from app.models.company import Company
from app.models.final_site import FinalSite
from app.models.geography import City, Country, State


def _kit(**kw):
    primary, accent, background, text = category_palette("barbearia", "fr-FR")
    base = dict(name="Barbier Lumière", category_slug="barbearia", category_label="barbier", city="Paris",
                mood="bold", language="fr-FR", primary=primary, accent=accent, background=background, text=text)
    base.update(kw)
    return BrandKit(**base)


def test_missing_for_final_lista_o_que_falta():
    assert missing_for_final(_kit()) == ["endereco", "telefone", "servico com preco", "horario"]


def test_missing_for_final_vazio_com_tudo_real():
    completo = _kit(address="12 Rue de Charonne", phone="+33 1 23", services=[("Corte", "18 €")],
                    hours=["Mo-Fr 09:00-18:00"])
    assert missing_for_final(completo) == []


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
def empresa_incompleta(db):
    c = Company(name="Barbier Lumière", city_id=1, category_id=1, website="https://barbier-lumiere.fr",
                email="contact@barbier-lumiere.fr", preferred_channel="email", source="test",
                collected_at=datetime.now(timezone.utc))
    db.add(c)
    db.commit()
    db.add(Audit(company_id=c.id, digital_score=30, site_lang="fr", audited_at=datetime.now(timezone.utc)))
    db.commit()
    return c


@pytest.fixture
def empresa_completa(db):
    c = Company(name="Barbier Lumière", city_id=1, category_id=1, website="https://barbier-lumiere.fr",
                email="contact@barbier-lumiere.fr", address="12 Rue de Charonne", phone="+33 1 23 45 67 89",
                preferred_channel="email", source="test", collected_at=datetime.now(timezone.utc))
    db.add(c)
    db.commit()
    db.add(Audit(company_id=c.id, digital_score=30, site_lang="fr", audited_at=datetime.now(timezone.utc),
                 services_json=json.dumps([["Corte", "18 €"]]), opening_hours_json=json.dumps(["Mo-Fr 09:00-18:00"])))
    db.commit()
    return c


@pytest.fixture
def publisher(tmp_path):
    pub = PagesPublisher(root=tmp_path)
    pub.deploy = MagicMock(return_value="ok")
    return pub


@pytest.mark.asyncio
async def test_publish_recusa_sem_dado_real(db, empresa_incompleta, publisher):
    with patch("app.branding.brand_kit.pexels_photos", return_value=[]):
        with pytest.raises(FinalSiteError, match="endereco"):
            await FinalSiteService(db, publisher=publisher).publish(empresa_incompleta, photo_source=lambda q, n: [])
    assert db.query(FinalSite).count() == 0


@pytest.mark.asyncio
async def test_publish_recusa_sem_pages_configurado(db, empresa_completa, publisher):
    # Ambiente de teste nao tem CLOUDFLARE_* no .env, entao publisher.configured ja e False.
    with pytest.raises(FinalSiteError, match="Cloudflare"):
        await FinalSiteService(db, publisher=publisher).publish(empresa_completa, photo_source=lambda q, n: [])
    assert db.query(FinalSite).count() == 0


@pytest.mark.asyncio
async def test_publish_com_dado_completo(db, empresa_completa, publisher):
    with patch("app.branding.publisher.settings") as s:
        s.pages_configured = True
        s.CLOUDFLARE_PAGES_PROJECT = "studio"
        site = await FinalSiteService(db, publisher=publisher).publish(empresa_completa, photo_source=lambda q, n: [])

    assert site.status == "publicado"
    assert site.public_url.endswith(f"/site/{site.slug}/")
    assert 'class="aviso"' not in site.html
    assert "18 €" in site.html
    assert publisher.deploy.called
    assert (publisher.final_dir(site.slug) / "index.html").exists()


@pytest.mark.asyncio
async def test_publish_de_novo_atualiza_a_mesma_linha(db, empresa_completa, publisher):
    service = FinalSiteService(db, publisher=publisher)
    with patch("app.branding.publisher.settings") as s:
        s.pages_configured = True
        s.CLOUDFLARE_PAGES_PROJECT = "studio"
        primeira = await service.publish(empresa_completa, photo_source=lambda q, n: [])
        segunda = await service.publish(empresa_completa, photo_source=lambda q, n: [])

    assert primeira.id == segunda.id
    assert primeira.slug == segunda.slug
    assert db.query(FinalSite).count() == 1
