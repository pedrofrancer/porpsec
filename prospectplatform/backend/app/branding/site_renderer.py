"""Renderiza a previa (HTML unico, CSS inline) a partir do BrandKit. Sem LLM no layout."""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.branding.brand_kit import BrandKit, category_copy, load_copy
from app.i18n import lang_key

_TEMPLATES = Path(__file__).resolve().parent / "templates"

# Pares de fontes por mood (Google Fonts). Nada de Inter em tudo: cada categoria com a sua cara.
FONTS = {
    "bold": {"url": "Anton&family=Archivo:wght@400;600", "display": "'Anton', Impact, sans-serif",
             "body": "'Archivo', system-ui, sans-serif"},
    "soft": {"url": "Fraunces:opsz,wght@9..144,500;9..144,600&family=Karla:wght@400;600",
             "display": "'Fraunces', Georgia, serif", "body": "'Karla', system-ui, sans-serif"},
    "warm": {"url": "DM+Serif+Display&family=Work+Sans:wght@400;600",
             "display": "'DM Serif Display', Georgia, serif", "body": "'Work Sans', system-ui, sans-serif"},
    "clean": {"url": "Manrope:wght@400;600;700", "display": "'Manrope', system-ui, sans-serif",
              "body": "'Manrope', system-ui, sans-serif"},
}


def _relative_luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(hex_color: str) -> str:
    """Branco ou quase-preto, o que tiver mais contraste WCAG sobre o fundo dado."""
    try:
        dark, light = "#111111", "#ffffff"
        return dark if contrast_ratio(hex_color, dark) >= contrast_ratio(hex_color, light) else light
    except (ValueError, TypeError, IndexError):
        return "#ffffff"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters["on"] = readable_on
    return env


def _fmt(text: str, **values) -> str:
    return text.format(**values) if text else text


def render_site(kit: BrandKit, sender_brand: str) -> str:
    copy = load_copy()
    key = lang_key(kit.language)
    ui_raw = copy["ui"].get(key, copy["ui"]["en"])
    cat = category_copy(copy, kit.category_slug)
    cat_lang = cat.get(key, cat["en"])

    values = {"name": kit.name, "city": kit.city, "category": kit.category_label.capitalize(),
              "brand": sender_brand or "", "credit": ", ".join(sorted({p.credit for p in kit.gallery if p.credit}))}
    ui = {k: _fmt(v, **values) if k not in ("rating",) else v for k, v in ui_raw.items()}
    page_copy = {
        "tagline": _fmt(cat_lang["tagline"], **values),
        "cta": cat_lang["cta"],
        "about": _fmt(cat_lang["about"], **values),
        "services": cat_lang.get("services", []),
    }

    rating_line = None
    if kit.rating and kit.review_count:
        rating = f"{kit.rating:.1f}".replace(".", "," if key in ("fr", "nl", "pt") else ".")
        rating_line = ui_raw["rating"].format(rating=rating, count=kit.review_count)

    return _env().get_template("site.html.j2").render(
        kit=kit,
        lang=kit.language,
        ui=ui,
        copy=page_copy,
        fonts=FONTS[kit.mood],
        rating_line=rating_line,
        map_query=kit.address or f"{kit.name} {kit.city}",
        year=datetime.now().year,
    )
