from datetime import datetime
from sqlalchemy import Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
from app.models.base import TimestampMixin


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), nullable=False)
    neighborhood_id: Mapped[int | None] = mapped_column(ForeignKey("neighborhoods.id"))
    address: Mapped[str | None] = mapped_column(String(500))

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    subcategory_id: Mapped[int | None] = mapped_column(ForeignKey("subcategories.id"))

    phone: Mapped[str | None] = mapped_column(String(30))
    website: Mapped[str | None] = mapped_column(String(500))
    instagram: Mapped[str | None] = mapped_column(String(200))

    google_place_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    google_rating: Mapped[float | None] = mapped_column(Float)
    google_review_count: Mapped[int | None] = mapped_column(Integer)
    google_url: Mapped[str | None] = mapped_column(String(500))

    source: Mapped[str] = mapped_column(String(50), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    city: Mapped["City"] = relationship()
    neighborhood: Mapped["Neighborhood | None"] = relationship()
    category: Mapped["Category"] = relationship()
    subcategory: Mapped["Subcategory | None"] = relationship()

    audits: Mapped[list["Audit"]] = relationship(back_populates="company")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="company")
    messages: Mapped[list["Message"]] = relationship(back_populates="company")
