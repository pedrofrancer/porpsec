import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm import email_agent
from app.sending.email_validator import validate_email

URL = "https://desire-previews.pages.dev/p/barbier-lumiere-a1b2c3/"


def company(name="Barbier Lumière"):
    return SimpleNamespace(name=name, category=SimpleNamespace(slug="barbearia", name="Barbearia"),
                           city=SimpleNamespace(name="Paris"))


def audit(**kw):
    base = dict(has_viewport=False, response_time_ms=1500, has_scheduling=True, has_https=True)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("lang", ["fr-FR", "nl-NL", "pt-PT"])
def test_frase_fixa_com_link_leva_a_previa_e_passa_na_validacao(lang):
    draft = email_agent.fallback_email(company(), audit(), lang, URL)
    assert draft.body.count(URL) == 1
    assert f"\n\n{URL}\n\n" in draft.body
    ok, error = validate_email(draft.subject, draft.body, "Barbier Lumière", URL)
    assert ok, error


def test_frase_fixa_sem_link_continua_oferecendo():
    draft = email_agent.fallback_email(company(), audit(), "fr-FR")
    assert "http" not in draft.body
    assert "Je vous l'envoie ?" in draft.body


def test_validador_recusa_link_que_nao_e_a_previa():
    body = email_agent.fallback_email(company(), audit(), "fr-FR", URL).body
    ok, error = validate_email("le site", body + " https://outro.com", "Barbier Lumière", URL)
    assert not ok and "Link fora da previa" in error


def test_validador_recusa_previa_alterada_ou_ausente():
    body = email_agent.fallback_email(company(), audit(), "fr-FR", URL).body
    ok, error = validate_email("le site", body.replace(URL, URL + "x"), "Barbier Lumière", URL)
    assert not ok and "exatamente uma vez" in error


def test_validador_sem_previa_segue_recusando_qualquer_link():
    body = email_agent.fallback_email(company(), audit(), "fr-FR", URL).body
    ok, error = validate_email("le site", body, "Barbier Lumière")
    assert not ok


@pytest.mark.asyncio
async def test_prompt_com_previa_entrega_o_link_e_o_exemplo_certo():
    client = SimpleNamespace(is_configured=True, chat=AsyncMock(return_value='{"subject": "s", "body": "b"}'))
    with patch.object(email_agent, "LLMClient", return_value=client), \
            patch.object(email_agent, "_build_context", return_value="ctx"):
        await email_agent.generate_outreach_email(company(), audit(), [], None, "pt-PT", URL)
    system = client.chat.call_args.args[0]
    assert URL in system
    assert "exactly one link" in system
    assert "O que acham?" in system
    assert "Quer que envie?" not in system


@pytest.mark.asyncio
async def test_prompt_sem_previa_continua_sem_link():
    client = SimpleNamespace(is_configured=True, chat=AsyncMock(return_value='{"subject": "s", "body": "b"}'))
    with patch.object(email_agent, "LLMClient", return_value=client), \
            patch.object(email_agent, "_build_context", return_value="ctx"):
        await email_agent.generate_outreach_email(company(), audit(), [], None, "pt-PT")
    system = client.chat.call_args.args[0]
    assert "no links," in system
    assert "Quer que envie?" in system
