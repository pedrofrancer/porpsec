import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import ensure_schema
from app.models.base import Base
import app.models  # noqa: F401

NEW_COMPANY_COLS = ("email", "email_source", "preferred_channel")
NEW_AUDIT_COLS = ("site_lang", "emails_found", "legal_entity_signal", "logo_url",
                  "dominant_colors", "og_image_url", "about_snippet")


def _url(tmp_path, name):
    return f"sqlite:///{(tmp_path / name).as_posix()}"


def _cols(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_fresh_db_is_created_and_stamped(tmp_path):
    url = _url(tmp_path, "fresh.db")
    engine = create_engine(url)
    assert ensure_schema(engine, url) == "created"
    assert set(NEW_COMPANY_COLS) <= _cols(engine, "companies")
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar()
    # segunda chamada nao quebra
    assert ensure_schema(engine, url) == "upgraded"


def test_legacy_db_without_alembic_version_is_upgraded(tmp_path):
    url = _url(tmp_path, "legacy.db")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    # simula banco criado antes desta versao: sem colunas novas e sem alembic_version
    with engine.begin() as conn:
        for col in NEW_COMPANY_COLS:
            conn.execute(text(f"ALTER TABLE companies DROP COLUMN {col}"))
        for col in NEW_AUDIT_COLS:
            conn.execute(text(f"ALTER TABLE audits DROP COLUMN {col}"))
    engine.dispose()

    engine = create_engine(url)
    assert "alembic_version" not in inspect(engine).get_table_names()
    assert ensure_schema(engine, url) == "upgraded"
    assert set(NEW_COMPANY_COLS) <= _cols(engine, "companies")
    assert set(NEW_AUDIT_COLS) <= _cols(engine, "audits")
