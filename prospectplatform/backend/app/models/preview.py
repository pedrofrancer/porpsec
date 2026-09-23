from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class SitePreview(Base):
    """Previa de site gerada na primeira resposta e o follow-up que leva o link.

    status: pendente -> rascunho -> publicado -> enviado  (ou erro / descartado)
    """

    __tablename__ = "site_previews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    reply_id: Mapped[int | None] = mapped_column(ForeignKey("inbound_replies.id"), unique=True)

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    template_slug: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str | None] = mapped_column(String(10))
    brand_kit_json: Mapped[str | None] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    preview_url: Mapped[str | None] = mapped_column(String(500))

    followup_subject: Mapped[str | None] = mapped_column(String(300))
    followup_text: Mapped[str | None] = mapped_column(Text)
    followup_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))

    last_error: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship()
    reply: Mapped["InboundReply | None"] = relationship()
