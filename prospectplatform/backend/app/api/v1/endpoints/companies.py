from fastapi import Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import math

from app.core.database import get_db
from app.models.company import Company
from app.models.geography import City
from app.models.category import Category
from app.schemas.company import (
    CompanyCreate, CompanyUpdate, CompanyRead, CompanyReadFull, PaginatedCompanies,
)


def get_companies(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    city_id: int | None = None,
    category_id: int | None = None,
    source: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Company)

    if city_id:
        query = query.filter(Company.city_id == city_id)
    if category_id:
        query = query.filter(Company.category_id == category_id)
    if source:
        query = query.filter(Company.source == source)
    if search:
        query = query.filter(Company.name.ilike(f"%{search}%"))

    total = query.count()
    pages = math.ceil(total / size) if total > 0 else 1
    items = query.offset((page - 1) * size).limit(size).all()

    return PaginatedCompanies(
        items=items, total=total, page=page, size=size, pages=pages
    )


def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None
    city = db.query(City).filter(City.id == company.city_id).first()
    category = db.query(Category).filter(Category.id == company.category_id).first()
    return CompanyReadFull(
        **CompanyRead.model_validate(company).model_dump(),
        city_name=city.name if city else "",
        category_name=category.name if category else "",
    )


def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    company = Company(
        **data.model_dump(),
        collected_at=data.collected_at or datetime.now(timezone.utc),
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def update_company(company_id: int, data: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company


def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return False
    db.delete(company)
    db.commit()
    return True
