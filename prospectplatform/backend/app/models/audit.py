from datetime import datetime
from sqlalchemy import Integer, String, Boolean, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)

    digital_score: Mapped[int] = mapped_column(Integer, nullable=False)
    has_https: Mapped[bool | None] = mapped_column(Boolean)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    has_whatsapp: Mapped[bool | None] = mapped_column(Boolean)
    has_cta: Mapped[bool | None] = mapped_column(Boolean)
    has_form: Mapped[bool | None] = mapped_column(Boolean)
    has_scheduling: Mapped[bool | None] = mapped_column(Boolean)
    has_meta_title: Mapped[bool | None] = mapped_column(Boolean)
    has_meta_description: Mapped[bool | None] = mapped_column(Boolean)

    raw_data: Mapped[str | None] = mapped_column(Text)

    audited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="audits")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="audit")
