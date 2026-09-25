from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.branding.final_site_service import FinalSiteError, FinalSiteService
from app.core.database import get_db
from app.models.company import Company
from app.models.final_site import FinalSite

router = APIRouter(prefix="/final-sites", tags=["final-sites"])


class FinalSiteOut(BaseModel):
    id: int
    company_id: int
    company_name: str
    status: str
    public_url: str | None
    published_at: str | None


def _out(site: FinalSite) -> FinalSiteOut:
    return FinalSiteOut(
        id=site.id, company_id=site.company_id, company_name=site.company.name, status=site.status,
        public_url=site.public_url, published_at=site.published_at.isoformat() if site.published_at else None,
    )


@router.post("/{company_id}", response_model=FinalSiteOut)
async def publish_final_site(company_id: int, db: Session = Depends(get_db)):
    """Publica o site final da empresa (endereco, telefone, servico com preco e horario reais).

    Falta algum desses fatos: 422 com o que falta, sem publicar nada.
    """
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    try:
        site = await FinalSiteService(db).publish(company)
    except FinalSiteError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _out(site)


@router.get("/{company_id}", response_model=FinalSiteOut)
def get_final_site(company_id: int, db: Session = Depends(get_db)):
    site = db.query(FinalSite).filter(FinalSite.company_id == company_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site final ainda nao existe pra essa empresa")
    return _out(site)
