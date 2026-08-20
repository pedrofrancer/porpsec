import asyncio
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import create_tables, SessionLocal
from app.core.logging_config import setup_logging
from app.api.v1.router import api_router

logger = logging.getLogger("dispatcher")

_dispatcher = None


def get_dispatcher():
    global _dispatcher
    if _dispatcher is None:
        from app.sending.dispatcher import Dispatcher
        _dispatcher = Dispatcher()
    return _dispatcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    create_tables()

    dispatcher = get_dispatcher()
    db = SessionLocal()
    dispatcher.replace_db(db)
    dispatcher._loop_task = asyncio.create_task(dispatcher.run_loop())
    logger.info("Dispatcher background loop agendado")

    yield

    dispatcher.stop()
    if hasattr(db, 'close'):
        db.close()
    logger.info("Dispatcher encerrado")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

static_dir = Path(__file__).resolve().parent.parent.parent / "interface"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
