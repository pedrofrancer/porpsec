"""Deixa o schema do banco em dia no startup, sem passo manual.

Bancos antigos nasceram de Base.metadata.create_all() e nao tem tabela alembic_version.
O schema deles corresponde a LEGACY_BASELINE; carimbamos essa revisao e seguimos com upgrade.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.config import settings
from app.models.base import Base

logger = logging.getLogger(__name__)

LEGACY_BASELINE = "c5254553fe9a"
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _alembic_config(url: str) -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["skip_logging"] = True
    return cfg


def ensure_schema(engine=None, url: str | None = None) -> str:
    """Cria ou migra o banco. Retorna a acao tomada (para log/teste)."""
    if engine is None:
        from app.core.database import engine as default_engine
        engine = default_engine
    url = url or settings.DATABASE_URL
    cfg = _alembic_config(url)
    tables = set(inspect(engine).get_table_names())

    import app.models  # noqa: F401 — registra todos os models

    if "companies" not in tables:
        Base.metadata.create_all(bind=engine)
        command.stamp(cfg, "head")
        action = "created"
    else:
        if "alembic_version" not in tables:
            command.stamp(cfg, LEGACY_BASELINE)
        command.upgrade(cfg, "head")
        # Tabelas novas sem migration propria (nenhuma hoje) seriam criadas aqui.
        Base.metadata.create_all(bind=engine)
        action = "upgraded"

    logger.info(f"Schema do banco: {action}")
    return action
