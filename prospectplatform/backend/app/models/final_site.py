from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class FinalSite(Base):
    """O site pronto pra empresa fechar: sem faixa de previa, indexavel, sem prazo. Um por
    empresa (republicar atualiza a mesma linha). So existe depois que endereco, telefone,
    servico com preco e horario forem reais (app.branding.final_site_service.missing_for_final)."""

    __tablename__ = "final_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, unique=True, index=True)

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="publicado")
    language: Mapped[str | None] = mapped_column(String(10))
    html: Mapped[str | None] = mapped_column(Text)
    public_url: Mapped[str | None] = mapped_column(String(500))

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship()
