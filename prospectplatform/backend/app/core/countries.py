from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"
_COUNTRIES_FILE = _CONFIG_DIR / "countries.yaml"
_TERMS_FILE = _CONFIG_DIR / "category_terms.yaml"

DEFAULT_COUNTRY = "BR"


@dataclass(frozen=True)
class CountrySettings:
    code: str
    name: str
    languages: tuple[str, ...]
    timezone: str
    maps_locale: str
    search_template: str
    send_window: tuple[int, int]
    outreach_enabled: bool
    channels: tuple[str, ...]
    require_legal_entity: bool
    legal_basis: str = ""

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def default_language(self) -> str:
        return self.languages[0]

    def resolve_language(self, site_lang: str | None) -> str:
        """Escolhe o idioma da mensagem: idioma do site se o pais aceita, senao o padrao."""
        if site_lang:
            prefix = site_lang.lower().split("-")[0]
            for lang in self.languages:
                if lang.lower() == site_lang.lower() or lang.lower().split("-")[0] == prefix:
                    return lang
        return self.default_language


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_countries() -> dict[str, CountrySettings]:
    raw = _load_yaml(_COUNTRIES_FILE).get("countries", {})
    result = {}
    for code, data in raw.items():
        window = data.get("send_window", [9, 19])
        result[code.upper()] = CountrySettings(
            code=code.upper(),
            name=data.get("name", code),
            languages=tuple(data.get("languages", ["en"])),
            timezone=data.get("timezone", "UTC"),
            maps_locale=data.get("maps_locale", "en"),
            search_template=data.get("search_template", "{term} {city}"),
            send_window=(int(window[0]), int(window[1])),
            outreach_enabled=bool(data.get("outreach_enabled", False)),
            channels=tuple(data.get("channels", [])),
            require_legal_entity=bool(data.get("require_legal_entity", False)),
            legal_basis=data.get("legal_basis", "") or "",
        )
    return result


def get_country(code: str | None) -> CountrySettings:
    countries = load_countries()
    code = (code or DEFAULT_COUNTRY).upper()
    if code not in countries:
        raise KeyError(f"Pais '{code}' nao configurado em config/countries.yaml")
    return countries[code]


def country_code_for_company(company) -> str:
    """Pais da empresa via cidade -> estado -> pais."""
    try:
        return company.city.state.country.code.upper()
    except AttributeError:
        return DEFAULT_COUNTRY


@lru_cache(maxsize=1)
def _load_terms() -> dict:
    return _load_yaml(_TERMS_FILE).get("terms", {})


def search_term(category_slug: str, category_name: str, locale: str) -> str:
    """Termo de busca da categoria no idioma do locale. Fallback: nome da categoria."""
    terms = _load_terms().get(category_slug, {})
    if locale in terms:
        return terms[locale]
    prefix = locale.split("-")[0]
    if prefix in terms and locale != "pt-BR":
        return terms[prefix]
    return category_name


def build_search_query(country: CountrySettings, category_slug: str, category_name: str, city_name: str) -> str:
    term = search_term(category_slug, category_name, country.maps_locale)
    return country.search_template.format(term=term, city=city_name)
