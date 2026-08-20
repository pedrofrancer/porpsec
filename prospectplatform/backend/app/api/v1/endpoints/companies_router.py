from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.company import Company
from app.api.v1.endpoints import companies as company_crud
from app.schemas.company import (
    CompanyCreate, CompanyUpdate, CompanyRead, CompanyReadFull, PaginatedCompanies,
)
from app.schemas.audit import DiagnosisReport

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/", response_model=PaginatedCompanies)
def list_companies(
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
    return company_crud.get_companies(
        page=page, size=size, city_id=city_id, category_id=category_id,
        source=source, min_score=min_score, max_score=max_score,
        search=search, db=db,
    )


@router.get("/{company_id}")
def read_company(company_id: int, db: Session = Depends(get_db)):
    result = company_crud.get_company(company_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return result


@router.post("/", response_model=CompanyRead, status_code=201)
def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    return company_crud.create_company(data, db)


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(company_id: int, data: CompanyUpdate, db: Session = Depends(get_db)):
    result = company_crud.update_company(company_id, data, db)
    if not result:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return result


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    if not company_crud.delete_company(company_id, db):
        raise HTTPException(status_code=404, detail="Empresa não encontrada")


@router.get("/{company_id}/diagnosis", response_model=DiagnosisReport)
def get_diagnosis(company_id: int, db: Session = Depends(get_db)):
    """Retorna diagnóstico completo da empresa (usa auditoria mais recente)."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    from app.models.audit import Audit
    from app.models.opportunity import Opportunity
    from app.api.v1.endpoints.diagnosis import build_diagnosis

    audit = db.query(Audit).filter(Audit.company_id == company_id).order_by(Audit.id.desc()).first()
    opportunities = db.query(Opportunity).filter(Opportunity.company_id == company_id).all()

    return build_diagnosis(company, audit, opportunities, db)


class OutreachMessage(BaseModel):
    company_id: int
    company_name: str
    phone: str | None
    message: str


@router.get("/{company_id}/outreach", response_model=OutreachMessage)
async def get_outreach_message(company_id: int, db: Session = Depends(get_db)):
    """Gera mensagem curta de abordagem consultiva via LLM."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    from app.models.audit import Audit
    from app.models.opportunity import Opportunity
    from app.api.v1.endpoints.diagnosis import build_diagnosis
    from app.llm.sales_agent import generate_outreach_message

    audit = db.query(Audit).filter(Audit.company_id == company_id).order_by(Audit.id.desc()).first()
    opportunities = db.query(Opportunity).filter(Opportunity.company_id == company_id).all()
    diagnosis = build_diagnosis(company, audit, opportunities, db)

    message = await generate_outreach_message(company, audit, opportunities, diagnosis)

    return OutreachMessage(
        company_id=company.id,
        company_name=company.name,
        phone=company.phone,
        message=message,
    )
