from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from sqlalchemy.orm import Session


@dataclass
class AuditResult:
    """Resultado de uma auditoria digital."""
    digital_score: int = 0
    has_https: bool | None = None
    response_time_ms: int | None = None
    has_whatsapp: bool | None = None
    has_cta: bool | None = None
    has_form: bool | None = None
    has_scheduling: bool | None = None
    has_meta_title: bool | None = None
    has_meta_description: bool | None = None
    meta_title_length: int | None = None
    meta_desc_length: int | None = None
    has_viewport: bool | None = None
    has_blog_content: bool | None = None
    blog_freshness_days: int | None = None
    instagram_exists: bool | None = None
    instagram_public: bool | None = None
    instagram_active: bool | None = None
    facebook_exists: bool | None = None
    facebook_active: bool | None = None
    google_business_complete: bool | None = None
    whatsapp_catalog_link: bool | None = None
    whatsapp_responds_badge: bool | None = None
    site_lang: str | None = None
    emails_found: list[str] = field(default_factory=list)
    legal_entity_signal: str | None = None
    logo_url: str | None = None
    dominant_colors: list[str] = field(default_factory=list)
    og_image_url: str | None = None
    about_snippet: str | None = None
    services: list[tuple[str, str]] = field(default_factory=list)
    opening_hours: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


class BaseAuditor(ABC):
    """Interface base para todos os auditores digitais."""

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def audit(self, company_id: int) -> AuditResult:
        """Executa a auditoria de uma empresa. Retorna AuditResult."""
        ...
