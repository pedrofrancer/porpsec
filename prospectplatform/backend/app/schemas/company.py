from pydantic import BaseModel, ConfigDict
from datetime import datetime


class CompanyBase(BaseModel):
    name: str
    city_id: int
    neighborhood_id: int | None = None
    address: str | None = None
    category_id: int
    subcategory_id: int | None = None
    phone: str | None = None
    website: str | None = None
    instagram: str | None = None
    facebook: str | None = None


class CompanyCreate(CompanyBase):
    source: str = "csv_import"
    collected_at: datetime | None = None
    google_place_id: str | None = None
    google_rating: float | None = None
    google_review_count: int | None = None
    google_url: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    city_id: int | None = None
    neighborhood_id: int | None = None
    address: str | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    phone: str | None = None
    website: str | None = None
    instagram: str | None = None
    google_rating: float | None = None
    google_review_count: int | None = None
    google_url: str | None = None


class CompanyRead(CompanyBase):
    id: int
    google_place_id: str | None
    google_rating: float | None
    google_review_count: int | None
    google_url: str | None
    source: str
    collected_at: datetime
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CompanyReadFull(CompanyRead):
    city_name: str = ""
    state_name: str = ""
    category_name: str = ""


class PaginatedCompanies(BaseModel):
    items: list[CompanyRead]
    total: int
    page: int
    size: int
    pages: int
