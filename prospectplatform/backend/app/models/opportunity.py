from datetime import datetime
from sqlalchemy import Integer, String, Boolean, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class OpportunityRule(Base):
    __tablename__ = "opportunity_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    condition_field: Mapped[str] = mapped_column(String(50), nullable=False)
    condition_operator: Mapped[str] = mapped_column(String(20), nullable=False)
    condition_value: Mapped[str | None] = mapped_column(String(100))
    required_categories: Mapped[str | None] = mapped_column(Text)

    suggested_solution: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="media")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    audit_id: Mapped[int | None] = mapped_column(ForeignKey("audits.id"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("opportunity_rules.id"))

    problem: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_solution: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="media")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="opportunities")
    audit: Mapped["Audit"] = relationship(back_populates="opportunities")
    rule: Mapped["OpportunityRule | None"] = relationship()
