from datetime import datetime
from sqlalchemy import Integer, String, Boolean, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)

    # Digital Score (0-100)
    digital_score: Mapped[int] = mapped_column(Integer, nullable=False)

    # WEBSITE
    has_https: Mapped[bool | None] = mapped_column(Boolean)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    has_whatsapp: Mapped[bool | None] = mapped_column(Boolean)
    has_cta: Mapped[bool | None] = mapped_column(Boolean)
    has_form: Mapped[bool | None] = mapped_column(Boolean)
    has_scheduling: Mapped[bool | None] = mapped_column(Boolean)
    has_meta_title: Mapped[bool | None] = mapped_column(Boolean)
    has_meta_description: Mapped[bool | None] = mapped_column(Boolean)
    meta_title_length: Mapped[int | None] = mapped_column(Integer)
    meta_desc_length: Mapped[int | None] = mapped_column(Integer)
    has_viewport: Mapped[bool | None] = mapped_column(Boolean)
    has_blog_content: Mapped[bool | None] = mapped_column(Boolean)
    blog_freshness_days: Mapped[int | None] = mapped_column(Integer)

    # REDES SOCIAIS
    instagram_exists: Mapped[bool | None] = mapped_column(Boolean)
    instagram_public: Mapped[bool | None] = mapped_column(Boolean)
    instagram_active: Mapped[bool | None] = mapped_column(Boolean)
    facebook_exists: Mapped[bool | None] = mapped_column(Boolean)
    facebook_active: Mapped[bool | None] = mapped_column(Boolean)
    google_business_complete: Mapped[bool | None] = mapped_column(Boolean)

    # WHATSAPP SIGNALS (inferência, não detecção direta)
    whatsapp_catalog_link: Mapped[bool | None] = mapped_column(Boolean)
    whatsapp_responds_badge: Mapped[bool | None] = mapped_column(Boolean)

    # CONTATO / JURIDICO (extraidos do site)
    site_lang: Mapped[str | None] = mapped_column(String(20))
    emails_found: Mapped[str | None] = mapped_column(Text)  # JSON list
    legal_entity_signal: Mapped[str | None] = mapped_column(String(50))

    # IDENTIDADE VISUAL (usada pelo BrandKitExtractor na hora da previa)
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    dominant_colors: Mapped[str | None] = mapped_column(Text)  # JSON list de hex
    og_image_url: Mapped[str | None] = mapped_column(String(1000))
    about_snippet: Mapped[str | None] = mapped_column(Text)
    services_json: Mapped[str | None] = mapped_column(Text)  # JSON list de [nome, preco]
    opening_hours_json: Mapped[str | None] = mapped_column(Text)  # JSON list de strings (schema.org)

    # Dados brutos extras
    raw_data: Mapped[str | None] = mapped_column(Text)

    audited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="audits")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="audit")
