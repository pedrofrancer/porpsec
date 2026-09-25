"""Publica as previas e os sites finais no Cloudflare Pages (plano gratis) com o wrangler oficial.

Um projeto so, duas pastas: /p/<slug>/ (previa, noindex, expira) e /site/<slug>/ (site final,
indexavel, sem prazo). Cada publicacao reenvia a arvore inteira (o wrangler so sobe o que
mudou). Nao e subdominio proprio por cliente: isso precisa de um dominio raiz configurado no
Cloudflare (custo e DNS por conta), que o piloto ainda nao tem. /site/<slug>/ e o
equivalente gratis, sem o cliente mexer em DNS.
"""

import logging
import os
import re
import secrets
import shutil
import subprocess
import unicodedata
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_ROBOTS = "User-agent: *\nDisallow: /p/\n"
_HEADERS = "/p/*\n  X-Robots-Tag: noindex, nofollow\n  Referrer-Policy: no-referrer\n"
_ROOT_INDEX = '<!doctype html><meta name="robots" content="noindex"><title>Preview</title>'


class PublishError(RuntimeError):
    pass


def make_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40] or "site"
    return f"{base}-{secrets.token_hex(3)}"


class PagesPublisher:
    def __init__(self, root: Path | None = None, runner=subprocess.run):
        self.root = root or settings.previews_dir
        self.runner = runner

    @property
    def configured(self) -> bool:
        return settings.pages_configured

    def page_dir(self, slug: str) -> Path:
        return self.root / "p" / slug

    def public_url(self, slug: str) -> str:
        return f"https://{settings.CLOUDFLARE_PAGES_PROJECT}.pages.dev/p/{slug}/"

    def final_dir(self, slug: str) -> Path:
        return self.root / "site" / slug

    def final_url(self, slug: str) -> str:
        return f"https://{settings.CLOUDFLARE_PAGES_PROJECT}.pages.dev/site/{slug}/"

    def _write_shared_files(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "robots.txt").write_text(_ROBOTS, encoding="utf-8")
        (self.root / "_headers").write_text(_HEADERS, encoding="utf-8")
        (self.root / "index.html").write_text(_ROOT_INDEX, encoding="utf-8")

    def write(self, slug: str, html: str) -> Path:
        """Grava a previa no disco (tambem servida localmente em /preview/<slug>/ para revisao)."""
        self._write_shared_files()
        target = self.page_dir(slug)
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(html, encoding="utf-8")
        return target

    def write_final(self, slug: str, html: str) -> Path:
        """Grava o site final: mesma arvore da previa, pasta /site/, sem o bloqueio de indexacao."""
        self._write_shared_files()
        target = self.final_dir(slug)
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(html, encoding="utf-8")
        return target

    def remove(self, slugs: list[str]):
        for slug in slugs:
            shutil.rmtree(self.page_dir(slug), ignore_errors=True)

    def _wrangler(self, *args: str) -> subprocess.CompletedProcess:
        npx = shutil.which("npx")
        if not npx:
            raise PublishError("npx nao encontrado: instale o Node.js (https://nodejs.org)")
        env = {**os.environ,
               "CLOUDFLARE_API_TOKEN": settings.CLOUDFLARE_API_TOKEN,
               "CLOUDFLARE_ACCOUNT_ID": settings.CLOUDFLARE_ACCOUNT_ID}
        return self.runner([npx, "--yes", "wrangler", *args], env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)

    def ensure_project(self):
        result = self._wrangler("pages", "project", "create", settings.CLOUDFLARE_PAGES_PROJECT,
                                "--production-branch", "main")
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0 and "already exists" not in output.lower():
            raise PublishError(f"Nao consegui criar o projeto no Pages: {output.strip()[-500:]}")

    def deploy(self) -> str:
        if not self.configured:
            raise PublishError("Cloudflare Pages nao configurado: defina CLOUDFLARE_API_TOKEN, "
                               "CLOUDFLARE_ACCOUNT_ID e CLOUDFLARE_PAGES_PROJECT no .env")
        self.ensure_project()
        result = self._wrangler("pages", "deploy", str(self.root),
                                "--project-name", settings.CLOUDFLARE_PAGES_PROJECT,
                                "--branch", "main", "--commit-dirty=true")
        if result.returncode != 0:
            raise PublishError(f"Deploy no Pages falhou: {((result.stdout or '') + (result.stderr or '')).strip()[-800:]}")
        logger.info("Previas publicadas no Cloudflare Pages")
        return result.stdout or ""
