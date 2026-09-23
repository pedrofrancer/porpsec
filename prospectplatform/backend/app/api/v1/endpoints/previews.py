from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.branding.preview_service import PreviewError, PreviewService
from app.core.database import get_db
from app.models.preview import SitePreview

router = APIRouter(prefix="/previews", tags=["previews"])


class PreviewOut(BaseModel):
    id: int
    company_id: int
    company_name: str
    status: str
    language: str | None
    template_slug: str | None
    local_url: str
    preview_url: str | None
    reply_text: str | None
    followup_subject: str | None
    followup_text: str | None
    last_error: str | None
    generated_at: str | None
    sent_at: str | None
    expires_at: str | None


class ApproveIn(BaseModel):
    followup_subject: str | None = None
    followup_text: str | None = None


def _out(p: SitePreview) -> PreviewOut:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return PreviewOut(
        id=p.id, company_id=p.company_id, company_name=p.company.name, status=p.status, language=p.language,
        template_slug=p.template_slug, local_url=f"/preview/p/{p.slug}/", preview_url=p.preview_url,
        reply_text=p.reply.raw_content if p.reply else None, followup_subject=p.followup_subject,
        followup_text=p.followup_text, last_error=p.last_error, generated_at=iso(p.generated_at),
        sent_at=iso(p.sent_at), expires_at=iso(p.expires_at),
    )


def _get(db: Session, preview_id: int) -> SitePreview:
    preview = db.get(SitePreview, preview_id)
    if not preview:
        raise HTTPException(status_code=404, detail="Previa nao encontrada")
    return preview


@router.get("", response_model=list[PreviewOut])
def list_previews(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(SitePreview)
    if status:
        query = query.filter(SitePreview.status == status)
    return [_out(p) for p in query.order_by(SitePreview.id.desc()).limit(200).all()]


@router.post("/{preview_id}/approve", response_model=PreviewOut)
async def approve(preview_id: int, data: ApproveIn, db: Session = Depends(get_db)):
    """Publica a previa no Cloudflare Pages e envia o follow-up no thread da empresa."""
    preview = _get(db, preview_id)
    try:
        await PreviewService(db).approve(preview, data.followup_subject, data.followup_text)
    except PreviewError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        preview.last_error = str(e)[:2000]
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))
    return _out(preview)


@router.post("/{preview_id}/regenerate", response_model=PreviewOut)
async def regenerate(preview_id: int, db: Session = Depends(get_db)):
    preview = _get(db, preview_id)
    service = PreviewService(db)
    try:
        service.reset(preview)
        await service.build_draft(preview)
    except PreviewError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _out(preview)


@router.post("/{preview_id}/discard", response_model=PreviewOut)
def discard(preview_id: int, db: Session = Depends(get_db)):
    preview = _get(db, preview_id)
    PreviewService(db).discard(preview)
    return _out(preview)
