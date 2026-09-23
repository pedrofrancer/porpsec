import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.inbound import InboundReply

router = APIRouter(prefix="/replies", tags=["replies"])


class ReplyOut(BaseModel):
    id: int
    company_id: int
    company_name: str | None
    kind: str
    is_first_reply: bool
    resulted_in_template: bool
    from_address: str | None
    subject: str | None
    raw_content: str
    received_at: str


@router.get("", response_model=list[ReplyOut])
def list_replies(kind: str | None = Query(None), limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    query = db.query(InboundReply)
    if kind:
        query = query.filter(InboundReply.kind == kind)
    rows = query.order_by(InboundReply.received_at.desc()).limit(limit).all()
    return [
        ReplyOut(
            id=r.id, company_id=r.company_id, company_name=r.company.name if r.company else None,
            kind=r.kind, is_first_reply=r.is_first_reply, resulted_in_template=r.resulted_in_template,
            from_address=r.from_address, subject=r.subject, raw_content=r.raw_content[:2000],
            received_at=r.received_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/status")
def listener_status():
    from app.main import get_reply_listener
    return get_reply_listener().status


@router.post("/poll")
async def poll_now():
    """Le a caixa agora (sem esperar o proximo ciclo)."""
    from app.main import get_reply_listener
    listener = get_reply_listener()
    if not listener.configured:
        raise HTTPException(status_code=400, detail="E-mail nao configurado no .env")
    count = await asyncio.to_thread(listener.poll_once)
    return {"registered": count}
