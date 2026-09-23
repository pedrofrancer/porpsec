from datetime import datetime
from sqlalchemy import Integer, String, Boolean, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class InboundReply(Base):
    """Resposta recebida a um outreach. external_id (Message-ID do e-mail) garante idempotencia."""

    __tablename__ = "inbound_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))

    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    from_address: Mapped[str | None] = mapped_column(String(254))
    subject: Mapped[str | None] = mapped_column(String(300))
    raw_content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="reply")  # reply | opt_out | bounce
    is_first_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    resulted_in_template: Mapped[bool] = mapped_column(Boolean, default=False)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship()
    message: Mapped["Message | None"] = relationship()
