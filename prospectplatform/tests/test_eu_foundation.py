import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest

from app.auditors.extractors import (
    clean_about_snippet,
    css_color_to_hex,
    detect_legal_entity,
    extract_emails,
    is_generic_local_part,
    is_webmail,
    normalize_lang,
    pick_brand_colors,
    pick_contact_email,
    registrable_domain,
)
from app.core.countries import build_search_query, get_country, search_term


# --- countries.yaml ---

def test_eu_countries_loaded():
    for code in ("PT", "BE", "FR", "NL"):
        c = get_country(code)
        assert c.outreach_enabled
        assert c.channels == ("email",)
        assert c.legal_basis


def test_spain_outreach_disabled():
    assert get_country("ES").outreach_enabled is False


def test_nl_requires_legal_entity():
    assert get_country("NL").require_legal_entity is True
    assert get_country("FR").require_legal_entity is False


def test_unknown_country_raises():
    with pytest.raises(KeyError):
        get_country("XX")


def test_belgium_language_follows_site():
    be = get_country("BE")
    assert be.resolve_language("nl") == "nl-BE"
    assert be.resolve_language("fr-BE") == "fr-BE"
    assert be.resolve_language(None) == "fr-BE"
    assert be.resolve_language("en") == "fr-BE"


def test_search_term_by_locale():
    assert search_term("barbearia", "Barbearia", "fr-FR") == "barbier"
    assert search_term("barbearia", "Barbearia", "nl-NL") == "kapper heren"
    assert search_term("academia", "Academia", "pt-PT") == "ginasio"
    # Brasil mantem o nome da categoria
    assert search_term("academia", "Academia", "pt-BR") == "Academia"
    assert search_term("inexistente", "Nome", "fr-FR") == "Nome"


def test_build_search_query():
    assert build_search_query(get_country("FR"), "barbearia", "Barbearia", "Paris") == "barbier Paris"
    assert build_search_query(get_country("PT"), "barbearia", "Barbearia", "Lisboa") == "barbearia em Lisboa"
    assert build_search_query(get_country("BR"), "barbearia", "Barbearia", "Cabo Frio") == "Barbearia em Cabo Frio"


# --- e-mail ---

def test_extract_emails_mailto_and_text():
    html = '<a href="mailto:Info@Salon-Lumiere.fr">x</a> ou contact@salon-lumiere.fr.'
    assert extract_emails(html) == ["info@salon-lumiere.fr", "contact@salon-lumiere.fr"]


def test_extract_emails_obfuscated():
    assert extract_emails("bonjour [at] kapsalon-mooi [dot] nl") == ["bonjour@kapsalon-mooi.nl"]
    assert extract_emails("geral (at) barbearia.pt") == ["geral@barbearia.pt"]


def test_extract_emails_ignores_junk():
    html = 'logo@2x.png abc@sentry.wixpress.com user@example.com real@shop.be'
    assert extract_emails(html) == ["real@shop.be"]


def test_registrable_domain():
    assert registrable_domain("https://www.salon.fr/contact") == "salon.fr"
    assert registrable_domain("salon.fr") == "salon.fr"
    assert registrable_domain("info@mail.salon.fr") == "salon.fr"
    assert registrable_domain("https://shop.co.uk") == "shop.co.uk"
    assert registrable_domain(None) is None


def test_webmail_and_generic():
    assert is_webmail("joao@sapo.pt")
    assert is_webmail("x@skynet.be")
    assert not is_webmail("info@salon.fr")
    assert is_generic_local_part("info@salon.fr")
    assert is_generic_local_part("contact.paris@salon.fr")
    assert not is_generic_local_part("jean.dupont@salon.fr")


def test_pick_contact_email_prefers_company_domain_generic():
    emails = ["jean@gmail.com", "jean.dupont@salon.fr", "contact@salon.fr"]
    assert pick_contact_email(emails, "https://www.salon.fr") == "contact@salon.fr"


def test_pick_contact_email_empty():
    assert pick_contact_email([], "https://salon.fr") is None


# --- forma juridica ---

@pytest.mark.parametrize("text,expected", [
    ("Kapsalon Mooi B.V. | KvK 12345678", "B.V."),
    ("© 2026 Barbershop Amsterdam BV", "B.V."),
    ("Holding N.V.", "N.V."),
    ("Salon Lumière SARL au capital de 1000 €", "SARL"),
    ("Coiffure Paris SAS - RCS Paris", "SAS"),
    ("Barbearia Lisboa, Lda. NIF 500000000", "Lda"),
    ("Bienvenue chez nous", None),
    ("Eenmanszaak Jan de Vries - KvK 1234", None),
])
def test_detect_legal_entity(text, expected):
    assert detect_legal_entity(text) == expected


# --- idioma / cores / sobre ---

def test_normalize_lang():
    assert normalize_lang("fr_be") == "fr-BE"
    assert normalize_lang("NL") == "nl"
    assert normalize_lang("") is None
    assert normalize_lang("{{lang}}") is None


def test_css_color_to_hex():
    assert css_color_to_hex("rgb(255, 0, 0)") == "#ff0000"
    assert css_color_to_hex("rgba(0, 0, 0, 0)") is None
    assert css_color_to_hex("#abc") == "#aabbcc"
    assert css_color_to_hex("transparent") is None


def test_pick_brand_colors_skips_neutrals():
    colors = ["rgb(255, 255, 255)", "rgb(0, 0, 0)", "rgb(200, 30, 60)",
              "rgb(200, 30, 60)", "rgb(20, 80, 160)", "rgb(128, 128, 128)"]
    assert pick_brand_colors(colors) == ["#c81e3c", "#1450a0"]


def test_clean_about_snippet():
    assert clean_about_snippet("curto") is None
    long_text = ("Fondé en 1998, notre salon accueille ses clients au coeur d'Ixelles. " * 8)
    snippet = clean_about_snippet(long_text)
    assert len(snippet) <= 320
    assert snippet.endswith(".")
