from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.prospection import ProspectingQueue, OptOut, ActionLog
from app.models.message import Message
from app.prospection.queue_manager import QueueManager

router = APIRouter(prefix="/prospection", tags=["prospection"])


class QueueEntryResponse(BaseModel):
    id: int
    company_id: int
    status: str
    notes: str | None
    created_at: str

    model_config = {"from_attributes": True}


class OptOutRequest(BaseModel):
    identifier: str
    reason: str | None = None


class OptOutResponse(BaseModel):
    id: int
    contact_identifier: str
    reason: str | None
    source: str | None
    created_at: str

    model_config = {"from_attributes": True}


class RateLimitStatus(BaseModel):
    sent_today: int
    daily_limit: int
    remaining: int
    can_send: bool


class MessageApprovalRequest(BaseModel):
    message_id: int


@router.get("/queue", response_model=list[QueueEntryResponse])
def get_queue(status: str | None = None, db: Session = Depends(get_db)):
    """Lista fila de prospecção."""
    manager = QueueManager(db)
    entries = manager.get_queue(status)
    return entries


@router.post("/queue/{company_id}", response_model=QueueEntryResponse)
def add_to_queue(company_id: int, notes: str | None = None, db: Session = Depends(get_db)):
    """Adiciona empresa à fila de prospecção."""
    manager = QueueManager(db)
    entry = manager.add_to_queue(company_id, notes)
    return entry


@router.post("/opt-out", response_model=OptOutResponse, status_code=201)
def register_opt_out(data: OptOutRequest, db: Session = Depends(get_db)):
    """Registra opt-out permanente."""
    manager = QueueManager(db)
    opt_out = manager.register_opt_out(data.identifier, data.reason)
    return opt_out


@router.get("/opt-outs", response_model=list[OptOutResponse])
def list_opt_outs(db: Session = Depends(get_db)):
    """Lista opt-outs registrados."""
    return db.query(OptOut).order_by(OptOut.created_at.desc()).all()


@router.get("/rate-limit", response_model=RateLimitStatus)
def get_rate_limit_status(db: Session = Depends(get_db)):
    """Retorna status do rate limit diário."""
    manager = QueueManager(db)
    sent = manager.get_send_count_today()

    from app.core.config import settings
    return RateLimitStatus(
        sent_today=sent,
        daily_limit=settings.DAILY_SEND_LIMIT,
        remaining=max(0, settings.DAILY_SEND_LIMIT - sent),
        can_send=manager.can_send_today(),
    )


@router.post("/approve/{message_id}")
def approve_message(message_id: int, db: Session = Depends(get_db)):
    """Aprova mensagem para envio."""
    manager = QueueManager(db)
    try:
        msg = manager.approve_message(message_id)
        return {"status": "aprovado", "message_id": msg.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send/{message_id}")
def mark_sent(message_id: int, db: Session = Depends(get_db)):
    """Marca mensagem como enviada."""
    manager = QueueManager(db)
    try:
        msg = manager.mark_sent(message_id)
        return {"status": "enviado", "message_id": msg.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
