"""Confere, sem enviar nada, se cada servico externo do .env responde de verdade.

Uso (na pasta prospectplatform):
    .venv\\Scripts\\python scripts\\verificar_config.py

Cada linha sai OK, FALHA ou AVISO, com o que fazer. Sai com codigo 1 se algo obrigatorio falhou.
"""

import imaplib
import os
import shutil
import smtplib
import ssl
import sys
from pathlib import Path

_backend = str(Path(__file__).resolve().parent.parent / "backend")
os.chdir(_backend)
sys.path.insert(0, _backend)

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = ""):
    results.append((status, name, detail))
    print(f"[{status:5}] {name}{': ' + detail if detail else ''}", flush=True)


def check(name: str, required: bool = True):
    """Decorador: excecao vira FALHA (ou AVISO, se opcional) com a mensagem da excecao."""
    def wrap(fn):
        def run():
            try:
                detail = fn()
                record("OK", name, detail or "")
            except Exception as e:  # o objetivo e relatar, nao parar
                record("FALHA" if required else "AVISO", name, str(e)[:300])
        return run
    return wrap


@check("Remetente e rodape legal")
def sender():
    missing = [k for k in ("SENDER_BRAND", "SENDER_POSTAL_ADDRESS") if not getattr(settings, k)]
    if missing:
        raise RuntimeError(f"faltando no .env: {', '.join(missing)} (obrigatorio no rodape na UE)")
    price = settings.OFFER_PRICE_RANGE or "sem preco no e-mail"
    return f"{settings.SENDER_BRAND} / {price}"


@check("SMTP do Gmail (login, sem envio)")
def smtp():
    if not (settings.EMAIL_ADDRESS and settings.EMAIL_APP_PASSWORD):
        raise RuntimeError("EMAIL_ADDRESS e EMAIL_APP_PASSWORD vazios")
    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ssl.create_default_context(), timeout=30) as s:
        s.login(settings.EMAIL_ADDRESS, settings.EMAIL_APP_PASSWORD)
    return settings.EMAIL_ADDRESS


@check("IMAP do Gmail (login e INBOX)")
def imap():
    if not (settings.EMAIL_ADDRESS and settings.EMAIL_APP_PASSWORD):
        raise RuntimeError("EMAIL_ADDRESS e EMAIL_APP_PASSWORD vazios")
    with imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT) as m:
        m.login(settings.EMAIL_ADDRESS, settings.EMAIL_APP_PASSWORD)
        status, data = m.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError(f"INBOX nao abriu: {data}")
    return f"{int(data[0])} mensagens no INBOX"


@check("LLM (uma chamada curta)")
def llm():
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY vazio: sem LLM o outreach usa frases fixas por idioma")
    resp = httpx.post(
        f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        json={"model": settings.LLM_MODEL, "messages": [{"role": "user", "content": "Responda: ok"}], "max_tokens": 5},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return settings.LLM_MODEL


@check("Cloudflare Pages (token e permissao)")
def cloudflare():
    if not settings.pages_configured:
        raise RuntimeError("CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID ou CLOUDFLARE_PAGES_PROJECT vazio")
    resp = httpx.get(
        f"https://api.cloudflare.com/client/v4/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}/pages/projects",
        headers={"Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}"},
        timeout=30,
    )
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or not body.get("success"):
        errors = "; ".join(e.get("message", "") for e in body.get("errors", [])) or resp.text[:200]
        raise RuntimeError(f"HTTP {resp.status_code}: {errors} (o token precisa de 'Cloudflare Pages: Edit')")
    names = [p["name"] for p in body.get("result", [])]
    state = "ja existe" if settings.CLOUDFLARE_PAGES_PROJECT in names else "sera criado no primeiro envio"
    return f"projeto {settings.CLOUDFLARE_PAGES_PROJECT} {state}"


@check("Node.js / npx (publicacao com wrangler)")
def node():
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx nao encontrado: instale o Node.js LTS")
    return npx


@check("Pexels (fotos ilustrativas)", required=False)
def pexels():
    if not settings.PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY vazio: previa sem foto propria fica so com cores e tipografia")
    resp = httpx.get("https://api.pexels.com/v1/search", params={"query": "barber", "per_page": 1},
                     headers={"Authorization": settings.PEXELS_API_KEY}, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return "chave valida"


@check("Playwright + Chromium (coleta e auditoria)")
def playwright():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        version = browser.version
        browser.close()
    return f"Chromium {version}"


@check("Banco de dados (schema em dia)")
def database():
    from app.core.migrations import ensure_schema
    return f"{ensure_schema()} em {settings.DATABASE_URL}"


@check("Envio automatico da previa", required=False)
def auto_send():
    if settings.PREVIEW_AUTO_SEND:
        raise RuntimeError("PREVIEW_AUTO_SEND=true: a previa sai sem sua revisao; recomendo false no primeiro dia")
    return "desligado (previa espera aprovacao no painel)"


def main():
    print("Verificando configuracao em backend/.env\n")
    for fn in (sender, smtp, imap, llm, cloudflare, node, pexels, playwright, database, auto_send):
        fn()
    failed = [r for r in results if r[0] == "FALHA"]
    print(f"\n{len(results) - len(failed)} de {len(results)} verificacoes sem falha.")
    if failed:
        print("Corrija as FALHAS antes de ligar o envio real.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
