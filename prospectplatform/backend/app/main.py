import asyncio
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.migrations import ensure_schema
from app.core.logging_config import setup_logging
from app.api.v1.router import api_router

logger = logging.getLogger("dispatcher")

_dispatcher = None
_reply_listener = None


def get_dispatcher():
    global _dispatcher
    if _dispatcher is None:
        from app.sending.dispatcher import Dispatcher
        _dispatcher = Dispatcher()
    return _dispatcher


def _reply_handler_factory():
    from app.branding.preview_service import enqueue_for_reply
    from app.inbound.reply_handler import ReplyEventHandler
    db = SessionLocal()
    handler = ReplyEventHandler(db, on_first_reply=lambda reply, company, outreach:
                                enqueue_for_reply(db, reply, company, outreach))
    return handler, db


def get_reply_listener():
    global _reply_listener
    if _reply_listener is None:
        from app.inbound.imap_listener import ImapReplyListener
        _reply_listener = ImapReplyListener(_reply_handler_factory)
    return _reply_listener


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    ensure_schema()

    dispatcher = get_dispatcher()
    db = SessionLocal()
    dispatcher.replace_db(db)
    dispatcher._loop_task = asyncio.create_task(dispatcher.run_loop())
    logger.info("Dispatcher background loop agendado")

    reply_listener = get_reply_listener()
    reply_listener.start()

    from app.branding.preview_service import PreviewWorker
    preview_worker = PreviewWorker(SessionLocal)
    preview_worker.start()

    yield

    preview_worker.stop()
    reply_listener.stop()
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

# Rascunhos das previas, para revisar antes de publicar (a versao publica fica no Cloudflare Pages).
settings.previews_dir.mkdir(exist_ok=True)
app.mount("/preview", StaticFiles(directory=str(settings.previews_dir), html=True), name="previews")

static_dir = Path(__file__).resolve().parent.parent.parent / "interface"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
