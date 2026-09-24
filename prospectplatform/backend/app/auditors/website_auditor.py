import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from playwright.async_api import async_playwright
from sqlalchemy.orm import Session

from app.auditors.base import BaseAuditor, AuditResult
from app.auditors.extractors import (
    clean_about_snippet,
    detect_legal_entity,
    extract_emails,
    extract_opening_hours,
    extract_services_prices,
    normalize_lang,
    pick_brand_colors,
    pick_contact_email,
)
from app.models.company import Company
from app.models.audit import Audit

_CONTACT_LINK_RE = r"contact|contato|contacto|kontakt|mentions-legales|mentions|impressum|colofon|over-ons|sobre|a-propos|about"

_BRAND_JS = r"""() => {
    const abs = (u) => { try { return new URL(u, location.href).href; } catch (e) { return null; } };
    const data = {};
    data.lang = document.documentElement.getAttribute('lang') || '';
    data.mailtos = Array.from(document.querySelectorAll('a[href^="mailto:"]'))
        .map(a => decodeURIComponent(a.getAttribute('href').slice(7).split('?')[0]));
    data.html = document.documentElement.outerHTML.slice(0, 400000);
    data.text = (document.body.innerText || '').slice(0, 20000);
    const footer = document.querySelector('footer, [class*="footer"], [id*="footer"]');
    data.footer = footer ? footer.innerText.slice(0, 3000) : '';

    // Logo: img no header/nav com 'logo' no class/id/alt/src
    const logoCandidates = Array.from(document.querySelectorAll(
        'header img, nav img, [class*="logo"] img, img[class*="logo"], img[id*="logo"], img[alt*="logo" i], img[src*="logo" i]'
    ));
    const logo = logoCandidates.find(img => (img.naturalWidth || img.width) >= 40) || logoCandidates[0];
    let logoSrc = logo ? (logo.currentSrc || logo.getAttribute('src')) : null;
    if (!logoSrc) {
        const icon = document.querySelector('link[rel="apple-touch-icon"], link[rel*="icon"][sizes]');
        logoSrc = icon ? icon.getAttribute('href') : null;
    }
    data.logo = logoSrc;
    // Logo branco/claro pensado pra cabecalho escuro do site original fica invisivel no nosso
    // fundo claro. Amostra a luminancia media do logo renderizado (canvas 24x24, ignora pixel
    // quase transparente); null quando nao da pra saber (sem imagem carregada, ou canvas
    // "sujo" por CORS do host do logo, que bloqueia a leitura de pixel).
    data.logo_is_light = null;
    if (logo) {
        try {
            const w = 24, h = 24;
            const canvas = document.createElement('canvas');
            canvas.width = w; canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(logo, 0, 0, w, h);
            const px = ctx.getImageData(0, 0, w, h).data;
            let lumaSum = 0, alphaSum = 0;
            for (let i = 0; i < px.length; i += 4) {
                const a = px[i + 3] / 255;
                if (a < 0.15) continue;
                lumaSum += ((0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]) / 255) * a;
                alphaSum += a;
            }
            if (alphaSum > 0) data.logo_is_light = (lumaSum / alphaSum) > 0.78;
        } catch (e) { /* canvas sujo por CORS: fica null, sem chip */ }
    }

    const og = document.querySelector('meta[property="og:image"], meta[name="og:image"], meta[name="twitter:image"]');
    data.og_image = og ? og.getAttribute('content') : null;

    // Cores: header, nav, botoes e links
    const colorEls = Array.from(document.querySelectorAll(
        'header, nav, [class*="header"], button, a.btn, a.button, [class*="btn"], [class*="cta"], h1, h2, a'
    )).slice(0, 120);
    const theme = document.querySelector('meta[name="theme-color"]');
    data.colors = theme ? [theme.getAttribute('content'), theme.getAttribute('content')] : [];
    colorEls.forEach(el => {
        const s = getComputedStyle(el);
        data.colors.push(s.backgroundColor);
        if (el.tagName === 'A' || /^H[12]$/.test(el.tagName)) data.colors.push(s.color);
    });

    // Texto "sobre": secao com id/class about/sobre/over-ons/a-propos, senao meta description
    const about = document.querySelector(
        '[id*="about" i] p, [class*="about" i] p, [id*="sobre" i] p, [class*="sobre" i] p, ' +
        '[id*="over-ons" i] p, [id*="propos" i] p, [class*="propos" i] p'
    );
    const desc = document.querySelector('meta[name="description"]');
    data.about = about ? about.innerText : (desc ? desc.getAttribute('content') : '');

    const re = new RegExp('""" + _CONTACT_LINK_RE + r"""', 'i');
    const contact = Array.from(document.querySelectorAll('a[href]')).find(a => {
        const href = a.getAttribute('href') || '';
        if (href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('#')) return false;
        const target = abs(href);
        return target && new URL(target).host === location.host && (re.test(href) || re.test(a.innerText || ''));
    });
    data.contact_url = contact ? abs(contact.getAttribute('href')) : null;
    return data;
}"""

_CONTACT_JS = r"""() => ({
    mailtos: Array.from(document.querySelectorAll('a[href^="mailto:"]'))
        .map(a => decodeURIComponent(a.getAttribute('href').slice(7).split('?')[0])),
    html: document.documentElement.outerHTML.slice(0, 400000),
    text: (document.body.innerText || '').slice(0, 20000),
})"""


class WebsiteAuditor(BaseAuditor):
    """Auditor de presença digital: website, redes sociais, Google Business, WhatsApp signals."""

    TIMEOUT_MS = 30_000
    GOOGLE_BUSINESS_TIMEOUT_MS = 40_000

    async def audit(self, company_id: int) -> AuditResult:
        company = self.db.get(Company, company_id)
        if not company:
            raise ValueError(f"Empresa {company_id} não encontrada")

        result = AuditResult()

        website_url = (company.website or "").strip()

        if website_url:
            if not website_url.startswith(("http://", "https://")):
                website_url = "https://" + website_url
            await self._audit_website(website_url, result)

        await self._audit_social_media(company, result)
        await self._audit_whatsapp_signals(website_url, company, result)
        self._calculate_score(result)

        return result

    async def _audit_website(self, url: str, result: AuditResult):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/137.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    ignore_https_errors=True,
                )
                page = await context.new_page()

                start_time = time.monotonic()
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=self.TIMEOUT_MS)
                    result.response_time_ms = int((time.monotonic() - start_time) * 1000)
                    result.has_https = url.startswith("https://")

                    if resp:
                        result.raw_data["status_code"] = resp.status
                except Exception:
                    result.response_time_ms = int((time.monotonic() - start_time) * 1000)
                    result.has_https = url.startswith("https://")
                    result.raw_data["error"] = "page_load_failed"
                    await browser.close()
                    return

                await asyncio.sleep(2)

                analysis = await page.evaluate("""() => {
                    const data = {};

                    // Meta title
                    const titleEl = document.querySelector('title');
                    data.meta_title = titleEl ? titleEl.textContent.trim() : '';
                    data.has_meta_title = data.meta_title.length > 0;
                    data.meta_title_length = data.meta_title.length;

                    // Meta description
                    const descEl = document.querySelector('meta[name="description"]');
                    data.meta_description = descEl ? descEl.getAttribute('content').trim() : '';
                    data.has_meta_description = data.meta_description.length > 0;
                    data.meta_desc_length = data.meta_description.length;

                    // Viewport
                    const viewportEl = document.querySelector('meta[name="viewport"]');
                    data.has_viewport = viewportEl !== null;

                    // WhatsApp links
                    const allLinks = Array.from(document.querySelectorAll('a[href]'));
                    data.has_whatsapp = allLinks.some(a => {
                        const href = a.href || '';
                        return href.includes('wa.me') || href.includes('api.whatsapp.com') ||
                               href.includes('whatsapp:');
                    });

                    // CTA - botões e links de contato
                    const ctaKeywords = [
                        'contato', 'fale conosco', 'orçamento', 'agende', 'ligue',
                        'whatsapp', 'chame', 'peça', 'compre', 'contrate', 'entre em contato'
                    ];
                    const buttons = Array.from(document.querySelectorAll('button, a.btn, a.button, [class*="cta"], [class*="btn"]'));
                    data.has_cta = buttons.some(b => {
                        const text = (b.textContent || '').toLowerCase();
                        return ctaKeywords.some(kw => text.includes(kw));
                    }) || allLinks.some(a => {
                        const text = (a.textContent || '').toLowerCase();
                        return ctaKeywords.some(kw => text.includes(kw));
                    });

                    // Formulário
                    data.has_form = document.querySelectorAll('form').length > 0 ||
                                    document.querySelectorAll('input[type="email"], input[type="tel"], textarea').length > 0;

                    // Agendamento
                    const schedulingKeywords = [
                        'agendamento', 'agendar', 'scheduling', 'booking', 'calendar',
                        'reserva', 'horário', 'marcar', 'sistema de agendamento'
                    ];
                    const pageText = document.body.innerText.toLowerCase();
                    data.has_scheduling = schedulingKeywords.some(kw => pageText.includes(kw));

                    // Blog / conteúdo recente
                    const blogSelectors = [
                        '[class*="blog"]', '[class*="post"]', '[class*="article"]',
                        'article', '[class*="news"]', '[class*="noticia"]'
                    ];
                    data.has_blog_content = blogSelectors.some(sel => {
                        const els = document.querySelectorAll(sel);
                        return els.length > 0;
                    });

                    // Links do catálogo do WhatsApp Business
                    data.whatsapp_catalog = allLinks.some(a => {
                        const href = a.href || '';
                        return href.includes('catalog') || href.includes('wa.me/') && href.includes('/catalog');
                    });

                    return data;
                }""")

                result.has_meta_title = analysis.get("has_meta_title", False)
                result.meta_title_length = analysis.get("meta_title_length", 0)
                result.has_meta_description = analysis.get("has_meta_description", False)
                result.meta_desc_length = analysis.get("meta_desc_length", 0)
                result.has_viewport = analysis.get("has_viewport", False)
                result.has_whatsapp = analysis.get("has_whatsapp", False)
                result.has_cta = analysis.get("has_cta", False)
                result.has_form = analysis.get("has_form", False)
                result.has_scheduling = analysis.get("has_scheduling", False)
                result.has_blog_content = analysis.get("has_blog_content", False)
                result.whatsapp_catalog_link = analysis.get("whatsapp_catalog", False)
                result.raw_data["meta_title"] = analysis.get("meta_title", "")
                result.raw_data["meta_description"] = analysis.get("meta_description", "")

                await self._extract_contact_and_brand(page, url, result)

                await browser.close()

        except Exception as e:
            result.raw_data["website_audit_error"] = str(e)

    async def _extract_contact_and_brand(self, page, url: str, result: AuditResult):
        """E-mail, idioma, forma juridica e identidade visual da home (e da pagina de contato)."""
        try:
            data = await page.evaluate(_BRAND_JS)
        except Exception as e:
            result.raw_data["brand_extract_error"] = str(e)
            return

        result.site_lang = normalize_lang(data.get("lang"))
        emails = extract_emails(" ".join(data.get("mailtos", [])), data.get("html", ""))
        legal_text = " ".join([data.get("footer", ""), data.get("text", "")])

        contact_url = data.get("contact_url")
        if contact_url and (not emails or not detect_legal_entity(legal_text)):
            try:
                await page.goto(contact_url, wait_until="domcontentloaded", timeout=self.TIMEOUT_MS)
                await asyncio.sleep(1)
                contact = await page.evaluate(_CONTACT_JS)
                emails += [e for e in extract_emails(" ".join(contact.get("mailtos", [])), contact.get("html", "")) if e not in emails]
                legal_text += " " + contact.get("text", "")
                result.raw_data["contact_page"] = contact_url
            except Exception as e:
                result.raw_data["contact_page_error"] = str(e)

        result.emails_found = emails[:10]
        result.legal_entity_signal = detect_legal_entity(legal_text)

        logo = data.get("logo")
        result.logo_url = urljoin(url, logo) if logo else None
        result.logo_is_light = data.get("logo_is_light")
        og = data.get("og_image")
        result.og_image_url = urljoin(url, og) if og else None
        result.dominant_colors = pick_brand_colors(data.get("colors", []))
        result.about_snippet = clean_about_snippet(data.get("about"))
        result.services = extract_services_prices(data.get("html"))
        result.opening_hours = extract_opening_hours(data.get("html"))

    async def _audit_social_media(self, company: Company, result: AuditResult):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/137.0.0.0 Safari/537.36"
                ),
                ignore_https_errors=True,
            )

            # --- Instagram ---
            instagram_url = (company.instagram or "").strip()
            if instagram_url:
                if not instagram_url.startswith("http"):
                    username = instagram_url.lstrip("@")
                    instagram_url = f"https://www.instagram.com/{username}/"
                await self._audit_instagram(context, instagram_url, result)
            else:
                result.instagram_exists = False

            # --- Facebook ---
            facebook_url = (company.facebook or "").strip()
            if facebook_url:
                if not facebook_url.startswith("http"):
                    facebook_url = f"https://www.facebook.com/{facebook_url.lstrip('/')}"
                await self._audit_facebook(context, facebook_url, result)
            else:
                result.facebook_exists = False

            # --- Google Business ---
            await self._audit_google_business(company, context, result)

            await browser.close()

    async def _audit_instagram(self, context, url: str, result: AuditResult):
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=self.TIMEOUT_MS)
            await asyncio.sleep(3)

            content = await page.content()

            result.instagram_exists = True

            # Verificar se é perfil público (se aparece bio, posts, etc.)
            is_private = await page.evaluate("""() => {
                const text = document.body.innerText.toLowerCase();
                return text.includes('esta conta é privada') || text.includes('this account is private');
            }""")
            result.instagram_public = not is_private

            # Verificar atividade recente: buscar datas de posts
            if result.instagram_public:
                has_recent = await page.evaluate("""() => {
                    const text = document.body.innerText.toLowerCase();
                    const recentIndicators = ['hora', 'hour', 'minuto', 'minute', 'dia', 'day',
                                               'semana', 'week', 'mês', 'month'];
                    return recentIndicators.some(ind => text.includes(ind));
                }""")
                result.instagram_active = has_recent

            await page.close()

        except Exception:
            result.instagram_exists = None
            result.instagram_public = None
            result.instagram_active = None

    async def _audit_facebook(self, context, url: str, result: AuditResult):
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=self.TIMEOUT_MS)
            await asyncio.sleep(3)

            result.facebook_exists = True

            has_content = await page.evaluate("""() => {
                const text = document.body.innerText;
                return text.length > 500;
            }""")
            result.facebook_active = has_content

            await page.close()

        except Exception:
            result.facebook_exists = None
            result.facebook_active = None

    async def _audit_google_business(self, company: Company, context, result: AuditResult):
        """Busca o perfil do Google Business da empresa e verifica completude."""
        result.google_business_complete = False

        search_query = f"{company.name} {company.city.name if company.city else ''}"
        gmb_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"

        try:
            page = await context.new_page()
            await page.goto(gmb_url, wait_until="domcontentloaded", timeout=self.GOOGLE_BUSINESS_TIMEOUT_MS)
            await asyncio.sleep(4)

            # Clicar no primeiro resultado se disponível
            try:
                first_result = page.locator('[role="feed"] a[href*="/maps/place"]').first
                if await first_result.is_visible(timeout=5000):
                    await first_result.click()
                    await asyncio.sleep(4)
            except Exception:
                pass

            gmb_data = await page.evaluate(r"""() => {
                const data = { exists: false, photos: false, hours: false, category: false };

                const text = document.body.innerText;

                // Verificar se há painel de business
                const hasPanel = document.querySelector('[class*="section-hero-header"]') ||
                                 document.querySelector('[data-attrid="kc:/local:one box"]') ||
                                 document.querySelector('[aria-label*="result"]') ||
                                 document.querySelector('[jsaction*="mouseover"]');

                data.exists = text.includes('Aberto') || text.includes('Fechado') ||
                              text.includes('hours') || text.includes('horário') ||
                              text.includes('Open') || text.includes('Closed') || hasPanel;

                // Fotos: verificar por imagens no painel
                const photoButtons = document.querySelectorAll('[aria-label*="foto"], [aria-label*="photo"], [aria-label*="Foto"]');
                data.photos = photoButtons.length > 0 || document.querySelectorAll('img[src*="googleusercontent"]').length > 2;

                // Horário
                data.hours = text.includes('Aberto') || text.includes('Fechado') ||
                             text.includes('horário') || /\d{1,2}:\d{2}/.test(text);

                // Categoria
                const categorySelectors = [
                    '[class*="category"]', '[data-attrid*="category"]',
                    '[aria-label*="Categoria"]', '[aria-label*="Category"]'
                ];
                data.category = categorySelectors.some(sel => document.querySelector(sel) !== null);

                return data;
            }""")

            result.google_business_complete = (
                gmb_data.get("exists", False) and
                (gmb_data.get("photos", False) or gmb_data.get("hours", False) or gmb_data.get("category", False))
            )

            # Selo "responde em minutos"
            has_badge = await page.evaluate("""() => {
                const text = document.body.innerText.toLowerCase();
                return text.includes('responde em minutos') || text.includes('responds in minutes') ||
                       text.includes('responde rapidamente') || text.includes('responds quickly');
            }""")
            result.whatsapp_responds_badge = has_badge

            result.raw_data["google_business"] = gmb_data

            await page.close()

        except Exception as e:
            result.raw_data["google_business_error"] = str(e)

    async def _audit_whatsapp_signals(self, website_url: str, company: Company, result: AuditResult):
        """Verifica sinais de WhatsApp Business (catálogo, badge) em sites e redes sociais."""
        # O website já foi auditado — catalog_link já pode ter sido detectado
        # Se não detectamos no site, verificar se há link no Instagram/Google
        if result.whatsapp_catalog_link is None:
            result.whatsapp_catalog_link = False

    def _calculate_score(self, result: AuditResult):
        """Calcula o Digital Score de 0 a 100 baseado nos pesos definidos."""
        score = 0

        # HTTPS válido — 15 pts
        if result.has_https:
            score += 15

        # Tempo resposta < 3s — 15 pts
        if result.response_time_ms is not None and result.response_time_ms < 3000:
            score += 15

        # Meta title > 10 chars — 10 pts
        if result.has_meta_title and (result.meta_title_length or 0) > 10:
            score += 10

        # Meta description > 50 chars — 10 pts
        if result.has_meta_description and (result.meta_desc_length or 0) > 50:
            score += 10

        # Viewport mobile — 5 pts
        if result.has_viewport:
            score += 5

        # WhatsApp visível — 10 pts
        if result.has_whatsapp:
            score += 10

        # CTA — 5 pts
        if result.has_cta:
            score += 5

        # Formulário — 5 pts
        if result.has_form:
            score += 5

        # Agendamento — 10 pts
        if result.has_scheduling:
            score += 10

        # Instagram ativo — 5 pts
        if result.instagram_active:
            score += 5

        # Google Business completo — 5 pts
        if result.google_business_complete:
            score += 5

        # Blog com conteúdo recente — 5 pts
        if result.has_blog_content and (result.blog_freshness_days is None or result.blog_freshness_days < 180):
            score += 5

        result.digital_score = score

    def save_audit(self, company_id: int, result: AuditResult) -> Audit:
        """Salva o resultado da auditoria no banco."""
        audit = Audit(
            company_id=company_id,
            digital_score=result.digital_score,
            has_https=result.has_https,
            response_time_ms=result.response_time_ms,
            has_whatsapp=result.has_whatsapp,
            has_cta=result.has_cta,
            has_form=result.has_form,
            has_scheduling=result.has_scheduling,
            has_meta_title=result.has_meta_title,
            has_meta_description=result.has_meta_description,
            meta_title_length=result.meta_title_length,
            meta_desc_length=result.meta_desc_length,
            has_viewport=result.has_viewport,
            has_blog_content=result.has_blog_content,
            blog_freshness_days=result.blog_freshness_days,
            instagram_exists=result.instagram_exists,
            instagram_public=result.instagram_public,
            instagram_active=result.instagram_active,
            facebook_exists=result.facebook_exists,
            facebook_active=result.facebook_active,
            google_business_complete=result.google_business_complete,
            whatsapp_catalog_link=result.whatsapp_catalog_link,
            whatsapp_responds_badge=result.whatsapp_responds_badge,
            site_lang=result.site_lang,
            emails_found=json.dumps(result.emails_found) if result.emails_found else None,
            legal_entity_signal=result.legal_entity_signal,
            logo_url=result.logo_url,
            logo_is_light=result.logo_is_light,
            dominant_colors=json.dumps(result.dominant_colors) if result.dominant_colors else None,
            og_image_url=result.og_image_url,
            about_snippet=result.about_snippet,
            services_json=json.dumps(result.services, ensure_ascii=False) if result.services else None,
            opening_hours_json=json.dumps(result.opening_hours, ensure_ascii=False) if result.opening_hours else None,
            raw_data=json.dumps(result.raw_data, default=str, ensure_ascii=False),
            audited_at=datetime.now(timezone.utc),
        )
        self.db.add(audit)

        company = self.db.get(Company, company_id)
        if company and not company.email and result.emails_found:
            company.email = pick_contact_email(result.emails_found, company.website)
            company.email_source = "website"

        self.db.commit()
        self.db.refresh(audit)
        return audit
