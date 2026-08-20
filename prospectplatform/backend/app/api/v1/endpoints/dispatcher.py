from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/dispatcher", tags=["dispatcher"])


def _get_dispatcher():
    from app.main import get_dispatcher
    return get_dispatcher()


class DispatcherStatus(BaseModel):
    running: bool
    paused: bool
    circuit_open: bool
    last_error: str | None
    consecutive_errors: int
    warmup_day: int
    warmup_max_today: int
    started_at: str | None
    last_cycle_at: str | None
    next_cycle_at: str | None
    loop_active: bool


@router.get("/status", response_model=DispatcherStatus)
def dispatcher_status():
    """Retorna status do dispatcher."""
    return _get_dispatcher().status


@router.post("/pause")
def dispatcher_pause():
    """Pausa o dispatcher."""
    _get_dispatcher().pause()
    return {"status": "paused"}


@router.post("/resume")
def dispatcher_resume():
    """Retoma o dispatcher."""
    _get_dispatcher().resume()
    return {"status": "resumed"}


@router.post("/run")
async def dispatcher_run():
    """Executa um ciclo manual do dispatcher."""
    d = _get_dispatcher()
    if d._running:
        return {"status": "already_running"}

    import asyncio
    asyncio.create_task(d.run_cycle())
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
