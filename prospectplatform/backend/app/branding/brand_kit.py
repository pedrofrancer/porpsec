"""Monta a identidade visual da empresa a partir do que a auditoria ja coletou.

Nada e inventado: sem logo vira logotipo tipografico com o nome, sem cores vira a paleta
do "mood" da categoria, sem foto propria vira foto de banco rotulada como ilustrativa.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
import yaml

from app.core.config import settings
from app.core.countries import search_term
from app.i18n import lang_key

logger = logging.getLogger(__name__)

_COPY_FILE = Path(__file__).resolve().parent.parent.parent.parent / "config" / "site_copy.yaml"

# Paletas de reserva por oficio (design-system.md, secao 3): (primaria, acento, fundo, texto).
# So entram quando o site nao deu cor nenhuma (brand_colors_from_site=False). Os materiais do
# oficio, nao um "mood" generico: couro e latao na barbearia, azulejo e cal no restaurante em
# PT, ardosia e giz no restaurante em FR, linho e terracota na pousada, branco clinico com um
# azul discreto na clinica. Restaurante muda de par por lingua (mercado FR/BE fala PT/FR/NL).
CATEGORY_PALETTES = {
    "barbearia": ("#3c2a1d", "#b8925a", "#1b1613", "#f3ead9"),
    "academia": ("#22262d", "#5b95b8", "#121316", "#eef1f4"),
    "salao-de-beleza": ("#8a5a52", "#cf9a86", "#faf3f0", "#2e2320"),
    "clinica": ("#25302f", "#2f6f8f", "#f7faf9", "#1c2624"),
    "restaurante": {
        "pt": ("#1f4d63", "#c7b98a", "#f5f2ea", "#20303a"),  # azulejo e cal
        "fr": ("#3a3f42", "#e8c468", "#2c2f31", "#f4f1ea"),  # ardosia e giz
    },
    "pousada": ("#b5623f", "#d8c3a5", "#f6efe6", "#3a2a20"),
    "imobiliaria": ("#4a5257", "#4f8fae", "#f1f2f2", "#1e2224"),
    "oficina": ("#2a2d31", "#d99a2b", "#17181b", "#eceef0"),
    "_default": ("#1f3a5f", "#3aa7a3", "#f6f8fa", "#1b1f24"),
}


def category_palette(slug: str, language: str) -> tuple[str, str, str, str]:
    """Paleta de reserva do oficio. Restaurante varia por lingua; sem par para a lingua, cai no FR
    (ardosia e giz), o par mais proximo de um bistro europeu generico entre os mercados do piloto."""
    entry = CATEGORY_PALETTES.get(slug, CATEGORY_PALETTES["_default"])
    if isinstance(entry, dict):
        return entry.get(lang_key(language), entry["fr"])
    return entry


@dataclass
class Photo:
    url: str
    credit: str | None = None  # "Nome / Pexels" quando for foto de banco


@dataclass
class BrandKit:
    name: str
    category_slug: str
    category_label: str
    city: str
    mood: str
    language: str
    primary: str
    accent: str
    background: str
    text: str
    logo_url: str | None = None
    hero: Photo | None = None
    gallery: list[Photo] = field(default_factory=list)
    stock_photos: bool = False
    about_snippet: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    instagram: str | None = None
    rating: float | None = None
    review_count: int | None = None
    brand_colors_from_site: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def load_copy() -> dict:
    with open(_COPY_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def category_copy(copy: dict, slug: str) -> dict:
    return copy["categories"].get(slug) or copy["categories"]["_default"]


def _luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def pexels_photos(query: str, count: int = 4) -> list[Photo]:
    """Fotos de banco gratis (Pexels). Sem chave ou com erro: lista vazia, a previa segue sem foto."""
    if not settings.PEXELS_API_KEY:
        return []
    try:
        resp = httpx.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": count, "orientation": "landscape"},
            headers={"Authorization": settings.PEXELS_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        return [
            Photo(url=p["src"]["large2x"], credit=f"{p['photographer']} / Pexels")
            for p in resp.json().get("photos", [])
        ]
    except Exception as e:
        logger.warning(f"Pexels indisponivel ({query}): {e}")
        return []


def photo_query_for(company) -> str:
    slug = company.category.slug if company.category else "_default"
    return category_copy(load_copy(), slug).get("photo_query", "small business")


def build_brand_kit(company, audit, language: str, photo_source=pexels_photos) -> BrandKit:
    copy = load_copy()
    slug = company.category.slug if company.category else "_default"
    cat = category_copy(copy, slug)
    mood = cat["mood"]
    primary, accent, background, text = category_palette(slug, language)

    site_colors = json.loads(audit.dominant_colors) if audit and audit.dominant_colors else []
    if site_colors:
        primary = site_colors[0]
        accent = site_colors[1] if len(site_colors) > 1 else accent
        # Fundo escuro no mood bold so faz sentido se a cor da marca for clara o bastante para ler.
        if mood == "bold" and _luminance(primary) < 0.25:
            primary, accent = accent, primary

    hero, gallery, stock = None, [], False
    if audit and audit.og_image_url:
        hero = Photo(url=audit.og_image_url)
    stock_needed = 4 if hero is None else 3
    stock_list = photo_source(cat.get("photo_query", "small business"), stock_needed)
    if stock_list:
        stock = True
        if hero is None:
            hero, stock_list = stock_list[0], stock_list[1:]
        gallery = stock_list

    label = search_term(slug, company.category.name if company.category else "", language)
    return BrandKit(
        name=company.name,
        category_slug=slug,
        category_label=label,
        city=company.city.name if company.city else "",
        mood=mood,
        language=language,
        primary=primary,
        accent=accent,
        background=background,
        text=text,
        logo_url=audit.logo_url if audit else None,
        hero=hero,
        gallery=gallery,
        stock_photos=stock,
        about_snippet=audit.about_snippet if audit else None,
        address=company.address,
        phone=company.phone,
        email=company.email,
        website=company.website,
        instagram=company.instagram,
        rating=company.google_rating,
        review_count=company.google_review_count,
        brand_colors_from_site=bool(site_colors),
    )
