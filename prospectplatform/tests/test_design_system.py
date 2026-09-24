"""Regras do design-system.md que dao para conferir por maquina. O resto e o checklist da secao 7."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import re

import pytest

from app.branding.brand_kit import BrandKit, CATEGORY_PALETTES, Photo, category_palette, load_copy
from app.branding.site_renderer import FONTS, FONTS_BY_CATEGORY, OBJETO_BY_CATEGORY, contrast_ratio, objeto_for, render_site

BANIDAS = ("Inter", "Roboto", "Poppins", "Montserrat")


def kit(slug="barbearia", mood="bold", language="fr-FR", **kw):
    primary, accent, background, text = category_palette(slug, language)
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


def _paletas_de_reserva():
    for slug, entry in CATEGORY_PALETTES.items():
        if isinstance(entry, dict):
            for lang, palette in entry.items():
                yield f"{slug}-{lang}", palette
        else:
            yield slug, entry


@pytest.mark.parametrize("slug,palette", list(_paletas_de_reserva()))
def test_paletas_de_reserva_passam_aa(slug, palette):
    _, _, background, text = palette
    assert contrast_ratio(background, text) >= 4.5


@pytest.mark.parametrize("slug", [s for s in load_copy()["categories"] if s != "_default"])
def test_toda_categoria_do_copy_tem_paleta(slug):
    copy = load_copy()
    lang = next(k for k in copy["categories"][slug] if k != "mood" and k != "photo_query")
    primary, accent, background, text = category_palette(slug, lang)
    assert contrast_ratio(background, text) >= 4.5


@pytest.mark.parametrize("slug,objeto", [(s, o) for s, o in OBJETO_BY_CATEGORY.items() if s != "pousada"])
def test_objeto_do_oficio_na_primeira_tela(slug, objeto):
    """Cada categoria do design-system.md (secao 4) usa o objeto certo, nao o quadro generico.

    Pousada tem regra propria (objeto-livro so com about_snippet): ver os dois testes dedicados
    a ela abaixo.
    """
    page = html(slug=slug)
    assert f'class="objeto objeto-{objeto}"' in page


def test_categoria_sem_objeto_proprio_cai_na_tabela():
    assert objeto_for(kit(slug="imobiliaria")) == "tabela"
    assert objeto_for(kit(slug="oficina")) == "tabela"


def test_clinica_troca_lista_de_servicos_por_marcacao():
    page = html(slug="clinica")
    assert 'class="objeto objeto-marcacao"' in page
    assert 'class="objeto objeto-tabela"' not in page
    assert "tel-grande" in page
    # Os tratamentos continuam na pagina, so que numa secao propria, sem cor de fundo.
    assert 'class="lista-sobria"' in page


def test_restaurante_e_academia_nao_ganham_pontilhado_de_preco():
    # O pontilhado imita a tabela de precos da barbearia; carta e quadro de horarios nao tem.
    assert "<i></i>" not in html(slug="restaurante")
    assert "<i></i>" not in html(slug="academia")
    assert "<i></i>" in html(slug="barbearia")


def test_pousada_abre_com_a_frase_sobre_quando_existe():
    page = html(slug="pousada", about_snippet="Casa antiga junto ao rio, aberta desde sempre.")
    assert 'class="objeto objeto-livro"' in page


def test_pousada_sem_frase_sobre_cai_na_tabela_de_servicos():
    page = html(slug="pousada")
    assert 'class="objeto objeto-livro"' not in page
    assert 'class="objeto objeto-tabela"' in page


def test_pousada_com_about_nao_repete_a_frase_na_secao_sobre():
    page = html(slug="pousada", about_snippet="Casa antiga junto ao rio, aberta desde sempre.")
    assert page.count("Casa antiga junto ao rio, aberta desde sempre.") == 1


def test_servico_real_coletado_ganha_do_texto_de_categoria():
    page = html(slug="barbearia", services=[("Corte", "18 €"), ("Barba", "12 €")])
    assert "<b>Corte</b>" in page
    assert "18 €" in page
    # o texto de categoria (generico) some quando ha dado real
    assert "Aux ciseaux ou à la tondeuse" not in page


def test_sem_servico_coletado_usa_texto_de_categoria():
    page = html(slug="barbearia")
    assert "Aux ciseaux ou à la tondeuse" in page


def test_horario_coletado_aparece_no_contato():
    page = html(hours=["Mo-Fr 09:00-18:00", "Sa 09:00-12:00"])
    assert "Mo-Fr 09:00-18:00" in page
    assert "Sa 09:00-12:00" in page


def test_sem_horario_nao_mostra_linha_nem_inventa_aberto_agora():
    page = html()
    assert "aberto agora" not in page.lower()
    assert "open now" not in page.lower()
