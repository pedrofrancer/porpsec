"""Site final: publicado quando o cliente fecha. Diferente da previa (preview_service.py):
sem faixa de "isso ainda nao e site publicado", indexavel, sem prazo de validade.

So publica com fato real completo (design-system.md, secao 8): endereco, telefone, servico
com preco e horario. Sem isso, FinalSiteError diz exatamente o que falta; nunca publica com
o texto de categoria que a previa usa como fallback, porque o cliente ja fechou achando que
aquilo era dado dele.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.branding import brand_kit
from app.branding.brand_kit import BrandKit
from app.branding.publisher import PagesPublisher, make_slug
from app.branding.site_renderer import render_site
from app.core.config import settings
from app.core.countries import country_code_for_company, get_country
from app.models.audit import Audit
from app.models.final_site import FinalSite

logger = logging.getLogger("final_sites")


class FinalSiteError(RuntimeError):
    pass


def missing_for_final(kit: BrandKit) -> list[str]:
    """Fatos que design-system.md (secao 8) exige reais antes do site virar final. Ordem de
    aparicao no documento."""
    missing = []
    if not kit.address:
        missing.append("endereco")
    if not kit.phone:
        missing.append("telefone")
    if not kit.services:
        missing.append("servico com preco")
    if not kit.hours:
        missing.append("horario")
    return missing


class FinalSiteService:
    def __init__(self, db: Session, publisher: PagesPublisher | None = None):
        self.db = db
        self.publisher = publisher or PagesPublisher()

    def _existing(self, company_id: int) -> FinalSite | None:
        return self.db.query(FinalSite).filter(FinalSite.company_id == company_id).first()

    def _language(self, company, audit) -> str:
        try:
            country = get_country(country_code_for_company(company))
            return country.resolve_language(audit.site_lang if audit else None)
        except KeyError:
            return "en"

    async def publish(self, company, photo_source=brand_kit.pexels_photos) -> FinalSite:
        """Monta o BrandKit, confere o dado real e so entao publica. Levanta FinalSiteError
        (sem escrever nada) quando falta algum fato exigido ou o Pages nao esta configurado."""
        audit = self.db.query(Audit).filter(Audit.company_id == company.id).order_by(Audit.id.desc()).first()
        language = self._language(company, audit)
        kit = brand_kit.build_brand_kit(company, audit, language, photo_source=photo_source)

        missing = missing_for_final(kit)
        if missing:
            raise FinalSiteError("Falta dado real pra publicar o site final: " + ", ".join(missing))
        if not self.publisher.configured:
            raise FinalSiteError("Cloudflare Pages nao configurado")

        html = render_site(kit, settings.SENDER_BRAND, final=True)
        site = self._existing(company.id)
        if site is None:
            site = FinalSite(company_id=company.id, slug=make_slug(company.name))
            self.db.add(site)

        self.publisher.write_final(site.slug, html)
        await asyncio.to_thread(self.publisher.deploy)

        site.language = language
        site.html = html
        site.public_url = self.publisher.final_url(site.slug)
        site.status = "publicado"
        site.published_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.info(f"Site final publicado: {company.name} ({site.slug})")
        return site
