"""Regras do design-system.md que dao para conferir por maquina. O resto e o checklist da secao 7."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import re

import pytest

from app.branding.brand_kit import BrandKit, MOOD_PALETTES, Photo, load_copy
from app.branding.site_renderer import FONTS, FONTS_BY_CATEGORY, contrast_ratio, render_site

BANIDAS = ("Inter", "Roboto", "Poppins", "Montserrat")


def kit(slug="barbearia", mood="bold", language="fr-FR", **kw):
    primary, accent, background, text = MOOD_PALETTES[mood]
    base = dict(name="Atelier Lumière", category_slug=slug, category_label="barbier", city="Paris", mood=mood,
                language=language, primary=primary, accent=accent, background=background, text=text,
                address="12 rue Oberkampf, 75011 Paris", phone="+33 1 23 45 67 89")
    base.update(kw)
    return BrandKit(**base)


def html(**kw):
    return render_site(kit(**kw), "Desire Systems")


@pytest.mark.parametrize("lang", ["fr-FR", "nl-NL", "pt-PT"])
def test_nada_da_lista_proibida(lang):
    page = html(language=lang)
    assert "<iframe" not in page
    assert "gradient" not in page
    assert "eyebrow" not in page
    assert not re.search(r">\s*0\d\s*<", page), "cartao numerado"
    assert "<script" not in page


def test_mapa_e_link_e_nao_embed():
    page = html()
    assert "https://www.google.com/maps/search/?api=1&amp;query=" in page


def test_orcamento_de_peso():
    assert len(html().encode()) < 60_000


@pytest.mark.parametrize("fonts", list(FONTS_BY_CATEGORY.values()) + list(FONTS.values()))
def test_nenhuma_fonte_de_assinatura_generica(fonts):
    for banida in BANIDAS:
        assert banida not in fonts["url"] and banida not in fonts["display"] and banida not in fonts["body"]


def test_toda_categoria_do_copy_tem_fonte():
    copy = load_copy()
    for slug, cat in copy["categories"].items():
        assert slug in FONTS_BY_CATEGORY or cat["mood"] in FONTS


def test_sem_foto_nao_reserva_espaco_de_foto():
    page = html()
    assert 'class="fotos"' not in page


def test_foto_de_banco_vem_rotulada():
    page = html(gallery=[Photo(url="https://x/1.jpg", credit="Ana / Pexels")], stock_photos=True)
    assert 'class="rotulo"' in page


def test_texto_do_site_entra_entre_aspas_do_idioma():
    assert "« Depuis toujours au coin de la rue. »" in html(about_snippet="Depuis toujours au coin de la rue.")
    assert "«Desde sempre na esquina.»" in html(language="pt-PT", about_snippet="Desde sempre na esquina.")


@pytest.mark.parametrize("mood", list(MOOD_PALETTES))
def test_paletas_de_reserva_passam_aa(mood):
    _, _, background, text = MOOD_PALETTES[mood]
    assert contrast_ratio(background, text) >= 4.5
