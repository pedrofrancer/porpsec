import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm import email_agent
from app.llm.followup_agent import fallback_followup, validate_followup
from app.sending.email_body import finish_email, signature_name
from app.sending.email_validator import validate_email

URL = "https://studio.pages.dev/p/x-abc123/"


def company(name="Barbier Lumière"):
    return SimpleNamespace(name=name, category=SimpleNamespace(slug="barbearia", name="Barbearia"),
                           city=SimpleNamespace(name="Paris"))


def audit(**kw):
    base = dict(has_viewport=False, response_time_ms=1500, has_scheduling=True, has_https=True)
    base.update(kw)
    return SimpleNamespace(**base)


HUMILITY = {"fr-FR": "de l'extérieur", "nl-NL": "van buitenaf", "pt-PT": "Só vi de fora"}


@pytest.mark.parametrize("language", ["fr-FR", "nl-NL", "pt-PT"])
@pytest.mark.parametrize("signal", [dict(), dict(has_viewport=True, response_time_ms=7000),
                                    dict(has_viewport=True, has_scheduling=False),
                                    dict(has_viewport=True, has_https=False)])
def test_fallback_reads_like_a_person_and_passes_validation(language, signal):
    draft = email_agent.fallback_email(company(), audit(**signal), language)
    assert validate_email(draft.subject, draft.body, "Barbier Lumière") == (True, None)
    assert HUMILITY[language] in draft.body          # admite que so viu de fora
    assert draft.body.rstrip().endswith("?")          # termina com pergunta facil
    assert "\n- " not in draft.body                   # um problema, nao lista


@pytest.mark.parametrize("text,tell", [
    ("N'hésitez pas à me contacter.", "sitez pas"),
    ("Je peux booster tout ça.", "booster"),
    ("Wij bieden een oplossing op maat.", "oplossing"),
    ("Não hesite em responder.", "hesite"),
    ("Super, on en parle!", "!"),
])
def test_salesy_cliches_are_rejected(text, tell):
    body = email_agent.fallback_email(company(), audit(), "fr-FR").body + " " + text
    ok, error = validate_email("le site", body, "Barbier Lumière")
    assert not ok and tell in error


def test_finish_email_signs_with_first_name_before_footer():
    with patch("app.sending.email_body.settings") as s:
        s.SENDER_CONTACT_NAME, s.SENDER_BRAND = "Pedro Francisco", "Studio Nord"
        s.SENDER_POSTAL_ADDRESS, s.SENDER_WEBSITE = "Rua X 1, Lisboa", ""
        text = finish_email("Corpo.\n", "fr-FR", "Barbier Lumière")
        assert signature_name() == "Pedro"
    corpo, assinatura, rodape = text.split("\n\n", 2)
    assert corpo == "Corpo." and assinatura == "Pedro" and rodape.startswith("--")


def test_finish_email_falls_back_to_brand():
    with patch("app.sending.email_body.settings") as s:
        s.SENDER_CONTACT_NAME, s.SENDER_BRAND = "", "Studio Nord"
        s.SENDER_POSTAL_ADDRESS, s.SENDER_WEBSITE = "A", ""
        assert "\n\nStudio Nord\n\n--" in finish_email("Corpo.", "fr-FR", "X")


@pytest.mark.asyncio
async def test_prompt_carries_voice_example_and_sender():
    client = SimpleNamespace(is_configured=True,
                             chat=AsyncMock(return_value='{"subject": "votre site", "body": "Bonjour"}'))
    with patch.object(email_agent, "LLMClient", return_value=client), \
         patch.object(email_agent, "_build_context", return_value="dados"), \
         patch.object(email_agent.settings, "SENDER_CONTACT_NAME", "Pedro Francisco"), \
         patch.object(email_agent.settings, "OFFER_PRICE_RANGE", ""):
        await email_agent.generate_outreach_email(company(), audit(), [], None, "nl-NL")
    system = client.chat.call_args.args[0]
    assert "You are Pedro" in system and "herenkapper" in system and "Paris" in system
    assert "van buitenaf" in system          # exemplo holandes como ancora de tom
    assert "Do NOT sign" in system


@pytest.mark.parametrize("language", ["fr-FR", "nl-NL", "pt-PT", "en"])
def test_fallback_followup_is_valid_and_honest(language):
    text = fallback_followup("Barbier Lumière", language, URL, True, "490 EUR")
    assert validate_followup(text, URL) == (True, None)
    assert text.rstrip().endswith("?") and "490 EUR" in text


def test_termo_da_categoria_na_frase_nao_e_o_termo_de_busca():
    assert email_agent._category_term(company(), "nl-NL") == "herenkapper"
    assert email_agent._category_term(company(), "fr-FR") == "barbier"


def test_prompt_proibe_dizer_que_abriu_site_que_nao_existe():
    assert "NO website" in email_agent.SYSTEM_PROMPT
    assert "Never say you opened" in email_agent.SYSTEM_PROMPT


def test_rodape_frances_faz_elisao_do_nome():
    from app.i18n import legal_footer
    assert "l'adresse d'Atelier Nord" in legal_footer("fr-FR", "B", "A", "Atelier Nord")
    assert "l'adresse de Barbier Lumière" in legal_footer("fr-FR", "B", "A", "Barbier Lumière")


def test_frases_fixas_nao_supoem_genero_nem_esquecem_elisao():
    fr = email_agent.fallback_email(company("Atelier Nord"), audit(), "fr-FR")
    assert fr.subject == "le site d'Atelier Nord"
    pt = email_agent.fallback_email(company("Barbearia do Largo"), audit(), "pt-PT")
    assert "encontrei a " not in pt.body and "apareceu-me Barbearia do Largo" in pt.body
    assert pt.subject == "Barbearia do Largo: o vosso site"
    assert "o vosso contacto" in finish_email("Corpo.", "pt-PT", "Barbearia do Largo")
