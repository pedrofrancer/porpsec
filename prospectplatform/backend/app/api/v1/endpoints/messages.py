from pydantic import BaseModel
from fastapi import APIRouter, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.message import Message
from app.models.company import Company

router = APIRouter(prefix="/messages", tags=["messages"])


class MessageOut(BaseModel):
    id: int
    company_id: int
    company_name: str | None
    status: str
    message_text: str
    generated_at: str
    approved_at: str | None
    sent_at: str | None
    send_attempts: int
    last_error: str | None
    llm_model: str | None

    model_config = {"from_attributes": True}


class MessageStats(BaseModel):
    total: int
    rascunho: int
    aprovado: int
    enviado: int
    erro_envio: int
    erro_validacao: int
    enviado_hoje: int
    enviado_esta_hora: int


@router.get("", response_model=list[MessageOut])
def list_messages(
    status: str | None = Query(None, description="Filtrar por status"),
    company_id: int | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    db: Session = next(get_db())
    try:
        query = db.query(Message)
        if status:
            query = query.filter(Message.status == status)
        if company_id:
            query = query.filter(Message.company_id == company_id)
        query = query.order_by(Message.created_at.desc())
        rows = query.offset(offset).limit(limit).all()

        result = []
        for m in rows:
            company = db.get(Company, m.company_id)
            result.append(MessageOut(
                id=m.id,
                company_id=m.company_id,
                company_name=company.name if company else None,
                status=m.status,
                message_text=m.message_text[:200],
                generated_at=m.generated_at.isoformat() if m.generated_at else "",
                approved_at=m.approved_at.isoformat() if m.approved_at else None,
                sent_at=m.sent_at.isoformat() if m.sent_at else None,
                send_attempts=m.send_attempts,
                last_error=m.last_error,
                llm_model=m.llm_model,
            ))
        return result
    finally:
        db.close()


@router.get("/stats", response_model=MessageStats)
def message_stats():
    db: Session = next(get_db())
    try:
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_start = now.replace(minute=0, second=0, microsecond=0)

        def count_status(s):
            return db.query(func.count(Message.id)).filter(Message.status == s).scalar()

        enviado_hoje = db.query(func.count(Message.id)).filter(
            Message.status == "enviado", Message.sent_at >= today_start
        ).scalar()

        enviado_hora = db.query(func.count(Message.id)).filter(
            Message.status == "enviado", Message.sent_at >= hour_start
        ).scalar()

        return MessageStats(
            total=db.query(func.count(Message.id)).scalar(),
            rascunho=count_status("rascunho"),
            aprovado=count_status("aprovado"),
            enviado=count_status("enviado"),
            erro_envio=count_status("erro_envio"),
            erro_validacao=count_status("erro_validacao"),
            enviado_hoje=enviado_hoje,
            enviado_esta_hora=enviado_hora,
        )
    finally:
        db.close()
