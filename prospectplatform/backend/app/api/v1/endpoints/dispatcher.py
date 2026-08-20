from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/dispatcher", tags=["dispatcher"])

# Instância global do dispatcher
_dispatcher = None


def get_dispatcher(db: Session = Depends(get_db)):
    global _dispatcher
    if _dispatcher is None:
        from app.sending.dispatcher import Dispatcher
        _dispatcher = Dispatcher(db)
    return _dispatcher


class DispatcherStatus(BaseModel):
    running: bool
    paused: bool
    circuit_open: bool
    last_error: str | None
    consecutive_errors: int
    warmup_day: int
    warmup_max_today: int


@router.get("/status", response_model=DispatcherStatus)
def dispatcher_status(dispatcher=Depends(get_dispatcher)):
    """Retorna status do dispatcher."""
    return dispatcher.status


@router.post("/pause")
def dispatcher_pause(dispatcher=Depends(get_dispatcher)):
    """Pausa o dispatcher."""
    dispatcher.pause()
    return {"status": "paused"}


@router.post("/resume")
def dispatcher_resume(dispatcher=Depends(get_dispatcher)):
    """Retoma o dispatcher."""
    dispatcher.resume()
    return {"status": "resumed"}


@router.post("/run")
async def dispatcher_run(dispatcher=Depends(get_dispatcher)):
    """Executa um ciclo manual do dispatcher."""
    if dispatcher._running:
        return {"status": "already_running"}

    import asyncio
    asyncio.create_task(dispatcher.run_cycle())
    return {"status": "cycle_started"}


@router.get("/warmup")
def warmup_status():
    """Retorna status do warm-up."""
    from app.sending.dispatcher import WarmupManager
    from app.core.config import settings
    return {
        "day_number": WarmupManager.get_day_number(),
        "max_today": WarmupManager.get_max_today(),
        "daily_limit": settings.DAILY_SEND_LIMIT,
        "curve": settings.warmup_curve_list,
    }
