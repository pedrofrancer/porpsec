from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.company import Company
from app.schemas.audit import AuditRead

router = APIRouter(prefix="/audits", tags=["audits"])


@router.post("/{company_id}/audit", response_model=AuditRead)
async def run_audit(company_id: int, db: Session = Depends(get_db)):
    """Executa auditoria digital completa de uma empresa."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    from app.auditors.website_auditor import WebsiteAuditor
    auditor = WebsiteAuditor(db)

    result = await auditor.audit(company_id)
    audit = auditor.save_audit(company_id, result)

    return audit
