import logging
import re
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector
from app.models.company import Company
from app.models.geography import City
from app.models.category import Category
from app.core.config import settings
from app.core.countries import build_search_query, get_country

logger = logging.getLogger(__name__)


_CONSENT_BUTTONS = [
    'button:has-text("Aceitar tudo")', 'button:has-text("Tout accepter")',
    'button:has-text("Alles accepteren")', 'button:has-text("Accept all")',
    'button:has-text("Aceptar todo")', 'button:has-text("Aceitar")',
]

# Prefixos de aria-label por idioma que o Maps coloca antes do valor.
_LABEL_PREFIXES = re.compile(
    r"^(Telefone|Ligar para|T[eé]l[eé]phone|Appeler le|Telefoonnummer|Bellen|Phone|Call|"
    r"Endere[cç]o|Adresse|Adres|Address|Direcci[oó]n|Tel[eé]fono|Llamar a)\s*:?\s*",
    re.I,
)


class GoogleMapsCollector(BaseCollector):
    """
    Coleta empresas no Google Maps via Playwright.
    Clica nos cards do feed para extrair dados detalhados.
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self._seen_place_ids: set[str] = set()

    def collect(
        self,
        category_slug: str,
        city_name: str,
        max_results: int = 60,
        headless: bool = True,
    ) -> dict:
        from playwright.sync_api import sync_playwright

        self.reset_stats()
        city = self.db.query(City).filter(City.name == city_name).first()
        if not city:
            raise ValueError(f"Cidade '{city_name}' não encontrada no banco.")

        category = self.db.query(Category).filter(Category.slug == category_slug).first()
        if not category:
            raise ValueError(f"Categoria '{category_slug}' não encontrada no banco.")

        country = get_country(city.state.country.code if city.state and city.state.country else None)
        query = build_search_query(country, category.slug, category.name, city_name)
        self._locale = country.maps_locale

        existing = self.db.query(Company.google_place_id).filter(
            Company.google_place_id.isnot(None)
        ).all()
        self._seen_place_ids = {row[0] for row in existing}

        logger.info(f"Buscando: '{query}' (max {max_results} resultados)")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale=self._locale,
            )
            page = context.new_page()

            try:
                self._search_google_maps(
                    page, query, city, category, max_results
                )
            finally:
                browser.close()

        logger.info(f"Coleta finalizada: {self.stats}")
        return self.stats

    def _search_google_maps(
        self, page, query: str, city: City, category: Category, max_results: int
    ):
        hl = self._locale.split("-")[0]
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}?hl={hl}"
        page.goto(url, wait_until="domcontentloaded", timeout=settings.GOOGLE_MAPS_TIMEOUT)
        time.sleep(6)

        # Fechar popup de cookies se existir
        try:
            for selector in _CONSENT_BUTTONS:
                btn = page.locator(selector)
                if btn.count() > 0:
                    btn.first.click()
                    time.sleep(1)
                    break
        except Exception:
            pass

        feed = page.locator('[role="feed"]')
        if feed.count() == 0:
            logger.warning("Nenhum container de resultados encontrado.")
            return

        collected = 0
        scroll_attempts = 0
        max_scrolls = max(max_results // 3, 10)
        seen_hrefs: set[str] = set()

        while collected < max_results and scroll_attempts < max_scrolls:
            # Pegar links do feed via JS
            links = page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="maps/place"]');
                    const results = [];
                    const seen = new Set();
                    links.forEach(l => {
                        const href = l.href;
                        if (!seen.has(href)) {
                            seen.add(href);
                            let name = l.getAttribute('aria-label') || '';
                            results.push({ href, name });
                        }
                    });
                    return results;
                }
            """)

            if not links:
                scroll_attempts += 1
                feed.evaluate("(el) => el.scrollTop = el.scrollHeight")
                time.sleep(2)
                continue

            for link_data in links:
                if collected >= max_results:
                    break

                href = link_data["href"]
                if href in seen_hrefs:
                    continue
                seen_hrefs.add(href)

                place_id = self._extract_place_id(href)
                if not place_id or place_id in self._seen_place_ids:
                    continue

                name = link_data["name"]
                if not name:
                    continue

                # Clicar no link para abrir o painel de detalhes
                try:
                    link_el = page.locator(f'a[href="{href}"]')
                    if link_el.count() > 0:
                        link_el.first.click()
                        time.sleep(3)

                        detail = self._extract_detail(page)

                        company = self._save_company(
                            name=name,
                            city=city,
                            category=category,
                            place_id=place_id,
                            detail=detail,
                            href=href,
                        )

                        if company:
                            collected += 1
                            self._seen_place_ids.add(place_id)
                except Exception as e:
                    self.stats["errors"] += 1
                    logger.debug(f"Erro ao processar '{name}': {e}")

                # Fechar painel e voltar para lista
                try:
                    page.keyboard.press("Escape")
                    time.sleep(1)
                except Exception:
                    pass

            # Scroll
            try:
                feed.evaluate("(el) => el.scrollTop = el.scrollHeight")
                time.sleep(2)
            except Exception:
                pass

            scroll_attempts += 1

    def _extract_detail(self, page) -> dict:
        detail = {
            "phone": None,
            "website": None,
            "address": None,
            "rating": None,
            "review_count": None,
            "instagram": None,
        }

        data = page.evaluate("""
            () => {
                const result = {};
                
                // Telefone
                const phoneBtn = document.querySelector('button[data-item-id*="phone"]');
                if (phoneBtn) {
                    const label = phoneBtn.getAttribute('aria-label') || '';
                    result.phone = label.replace('Telefone: ', '').replace('Ligar para ', '').trim();
                }
                
                // Website
                const webLink = document.querySelector('a[data-item-id*="authority"]');
                if (webLink) {
                    result.website = webLink.href;
                }
                
                // Endereco
                const addrBtn = document.querySelector('button[data-item-id*="address"]');
                if (addrBtn) {
                    const label = addrBtn.getAttribute('aria-label') || '';
                    result.address = label.replace('Endereço: ', '').trim();
                }
                
                // Rating - tentar diferentes seletores
                const ratingSelectors = [
                    'div.fontDisplayLarge',
                    'span.ceNzKf span[role="img"]',
                    'span[aria-label*="estrela"]',
                    'div[aria-label*="estrela"]',
                    'span[aria-label*="toile"]',
                    'span[aria-label*="ster"]',
                    'span[aria-label*="star"]',
                ];
                for (const sel of ratingSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.textContent || el.getAttribute('aria-label') || '';
                        const match = text.match(/\\d[,\\.]\\d/);
                        if (match) {
                            result.rating = match[0];
                            break;
                        }
                    }
                }
                
                // Reviews
                const reviewSelectors = [
                    'button[jsaction*="review"]',
                    'span[aria-label*="avaliação"]',
                    'span[aria-label*="avis"]',
                    'span[aria-label*="review"]',
                    'span[aria-label*="recensie"]',
                ];
                for (const sel of reviewSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.textContent || el.getAttribute('aria-label') || '';
                        const match = text.match(/(\\d[\\d.]*\\d|\\d)/);
                        if (match) {
                            result.review_count = match[1].replace(/\\./g, '');
                            break;
                        }
                    }
                }
                
                // Instagram
                const instaLink = document.querySelector('a[href*="instagram.com"]');
                if (instaLink) {
                    result.instagram = instaLink.href;
                }
                
                return result;
            }
        """)

        if data:
            detail.update(data)

        for key in ("phone", "address"):
            if detail.get(key):
                detail[key] = _LABEL_PREFIXES.sub("", detail[key]).strip() or None

        # Converter rating
        if detail.get("rating"):
            try:
                detail["rating"] = float(str(detail["rating"]).replace(",", "."))
            except (ValueError, TypeError):
                detail["rating"] = None

        # Converter review_count
        if detail.get("review_count"):
            try:
                detail["review_count"] = int(str(detail["review_count"]).replace(".", ""))
            except (ValueError, TypeError):
                detail["review_count"] = None

        return detail

    def _extract_place_id(self, href: str) -> str | None:
        match = re.search(r"!0x([0-9a-f]+)!", href)
        if match:
            return match.group(1)

        match = re.search(r"!1s(0x[0-9a-f]+):0x([0-9a-f]+)", href)
        if match:
            return f"{match.group(1)}:{match.group(2)}"

        match = re.search(r"/maps/place/([^/]+)", href)
        if match:
            return match.group(1)

        return None

    def _save_company(
        self,
        name: str,
        city: City,
        category: Category,
        place_id: str,
        detail: dict,
        href: str,
    ) -> Company | None:
        self.stats["total"] += 1

        if detail.get("phone"):
            existing = self.db.query(Company).filter(
                Company.phone == detail["phone"]
            ).first()
            if existing:
                self.stats["skipped_duplicates"] += 1
                return None

        instagram = detail.get("instagram")
        if instagram:
            instagram = instagram.rstrip("/").split("/")[-1] or None
            if instagram and not instagram.startswith("@"):
                instagram = f"@{instagram}"

        company = Company(
            name=name,
            city_id=city.id,
            category_id=category.id,
            phone=detail.get("phone"),
            website=detail.get("website"),
            instagram=instagram,
            address=detail.get("address"),
            google_place_id=place_id,
            google_rating=detail.get("rating"),
            google_review_count=detail.get("review_count"),
            google_url=href,
            source="google_maps",
            collected_at=datetime.now(timezone.utc),
        )
        self.db.add(company)
        self.db.flush()
        self.stats["imported"] += 1
        return company
