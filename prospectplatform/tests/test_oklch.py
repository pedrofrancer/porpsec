"""Variacao de cor por empresa (design-system.md, secao 3): mesmo material do oficio, tom
proprio por empresa, sem sortear cor aleatoria e sem estourar contraste."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import types

import pytest

from app.branding.brand_kit import CATEGORY_PALETTES, company_seed, varied_category_palette
from app.branding.oklch import hex_to_oklch, oklch_to_hex
from app.branding.site_renderer import contrast_ratio

SAMPLES = ["#3c2a1d", "#b8925a", "#1b1613", "#f3ead9", "#ffffff", "#000000", "#e8c468", "#2f6f8f"]


@pytest.mark.parametrize("hex_color", SAMPLES)
def test_oklch_roundtrip(hex_color):
    L, c, h = hex_to_oklch(hex_color)
    assert oklch_to_hex(L, c, h) == hex_color


def test_company_seed_e_estavel():
    company = types.SimpleNamespace(id=42, name="Barbearia do Zé", google_place_id=None)
    assert company_seed(company) == company_seed(company)


def test_company_seed_prefere_place_id_a_id():
    a = types.SimpleNamespace(id=1, name="A", google_place_id="ChIJabc")
    b = types.SimpleNamespace(id=2, name="A", google_place_id="ChIJabc")
    assert company_seed(a) == company_seed(b)


def test_company_seed_muda_por_empresa():
    a = types.SimpleNamespace(id=1, name="Barbearia A", google_place_id=None)
    b = types.SimpleNamespace(id=2, name="Barbearia B", google_place_id=None)
    assert company_seed(a) != company_seed(b)


def test_mesma_empresa_sempre_recebe_a_mesma_variacao():
    seed = company_seed(types.SimpleNamespace(id=7, name="Salao X", google_place_id=None))
    p1 = varied_category_palette("barbearia", "pt-PT", seed)
    p2 = varied_category_palette("barbearia", "pt-PT", seed)
    assert p1 == p2


def test_duas_empresas_da_mesma_categoria_nao_saem_identicas():
    primaries = {varied_category_palette("barbearia", "pt-PT", seed)[0] for seed in range(20)}
    assert len(primaries) > 1


def test_fundo_e_texto_nao_sao_afetados_pela_variacao():
    for seed in (0, 1, 999):
        _, _, background, text = varied_category_palette("clinica", "fr-FR", seed)
        base = CATEGORY_PALETTES["clinica"]
        assert (background, text) == (base[2], base[3])


@pytest.mark.parametrize("slug", [s for s in CATEGORY_PALETTES if s != "_default"])
def test_variacao_nao_derruba_contraste_aa_de_fundo_e_texto(slug):
    for seed in (0, 5, 42):
        _, _, background, text = varied_category_palette(slug, "fr-FR", seed)
        assert contrast_ratio(background, text) >= 4.5


def test_variacao_fica_dentro_de_uma_faixa_pequena_de_matiz():
    # A variacao e um tom do mesmo material, nao uma cor de outra familia.
    from app.branding.oklch import hex_to_oklch
    base_primary = CATEGORY_PALETTES["barbearia"][0]
    _, base_c, base_h = hex_to_oklch(base_primary)
    for seed in range(30):
        primary, _, _, _ = varied_category_palette("barbearia", "pt-PT", seed)
        _, c, h = hex_to_oklch(primary)
        delta_h = min(abs(h - base_h), 360 - abs(h - base_h))
        assert delta_h <= 15
        assert c <= base_c * 1.16 + 1e-6
