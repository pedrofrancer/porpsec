from sqlalchemy import Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    regions: Mapped[list["Region"]] = relationship(back_populates="country")
    states: Mapped[list["State"]] = relationship(back_populates="country")


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    country: Mapped["Country"] = relationship(back_populates="regions")
    states: Mapped[list["State"]] = relationship(back_populates="region")

    __table_args__ = ({"sqlite_autoincrement": True},)


class State(Base):
    __tablename__ = "states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    country: Mapped["Country"] = relationship(back_populates="states")
    region: Mapped["Region | None"] = relationship(back_populates="states")
    cities: Mapped[list["City"]] = relationship(back_populates="state")


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    state: Mapped["State"] = relationship(back_populates="cities")
    neighborhoods: Mapped[list["Neighborhood"]] = relationship(back_populates="city")

    __table_args__ = ({"sqlite_autoincrement": True},)


class Neighborhood(Base):
    __tablename__ = "neighborhoods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    city: Mapped["City"] = relationship(back_populates="neighborhoods")

    __table_args__ = ({"sqlite_autoincrement": True},)
