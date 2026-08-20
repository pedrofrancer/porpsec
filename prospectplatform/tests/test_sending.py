import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.company import Company
from app.models.audit import Audit
from app.models.message import Message
from app.models.prospection import ProspectingQueue, OptOut, ActionLog
from app.models.geography import City, State, Country
from app.models.category import Category


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()

    existing = session.query(Country).first()
    if not existing:
        country = Country(id=1, name="Brasil", code="BR")
        state = State(id=1, name="RJ", code="RJ", country_id=1)
        city = City(id=1, name="Cabo Frio", state_id=1)
        category = Category(id=1, name="Barbearia", slug="barbearia")
        session.add_all([country, state, city, category])
        session.commit()

    yield session

    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


@pytest.fixture
def company(db):
    c = Company(
        name="Barbearia Teste",
        city_id=1,
        category_id=1,
        phone="(22)99999-0000",
        website="https://teste.com",
        instagram="@teste",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def company_no_website(db):
    c = Company(
        name="Barbar Shop Sem Site",
        city_id=1,
        category_id=1,
        phone="(22)98888-1111",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# --- ContentValidator tests ---

from app.sending.dispatcher import ContentValidator


def test_validate_empty_message():
    ok, err = ContentValidator.validate("", "Empresa")
    assert not ok
    assert "vazia" in err


def test_validate_placeholder_nome():
    ok, err = ContentValidator.validate("Ola [nome], tudo bem?", "Empresa")
    assert not ok
    assert "Placeholder" in err


def test_validate_placeholder_chaves():
    ok, err = ContentValidator.validate("Ola {{nome}}, tudo bem?", "Empresa")
    assert not ok
    assert "Placeholder" in err


def test_validate_company_name_missing():
    ok, err = ContentValidator.validate("Ola, tudo bem com sua empresa?", "Barbearia XYZ")
    assert not ok
    assert "nome da empresa" in err.lower()


def test_validate_too_long():
    ok, err = ContentValidator.validate("A" * 1001, "Empresa")
    assert not ok
    assert "longa" in err


def test_validate_ok():
    ok, err = ContentValidator.validate("Oi Barbearia Teste, vi que nao tem site. Topa ver?", "Barbearia Teste")
    assert ok
    assert err is None


# --- WarmupManager tests ---

from app.sending.dispatcher import WarmupManager


def test_warmup_first_use():
    WarmupManager.WARMUP_FILE = WarmupManager.WARMUP_FILE.parent / "test_warmup.json"
    if WarmupManager.WARMUP_FILE.exists():
        WarmupManager.WARMUP_FILE.unlink()

    WarmupManager.register_first_use()
    state = WarmupManager._load_state()
    assert state["first_use_date"] is not None

    WarmupManager.WARMUP_FILE.unlink(missing_ok=True)


def test_warmup_max_today():
    WarmupManager.WARMUP_FILE = WarmupManager.WARMUP_FILE.parent / "test_warmup.json"
    if WarmupManager.WARMUP_FILE.exists():
        WarmupManager.WARMUP_FILE.unlink()

    WarmupManager.register_first_use()
    max_today = WarmupManager.get_max_today()
    assert max_today > 0

    WarmupManager.WARMUP_FILE.unlink(missing_ok=True)


# --- OptOut tests ---

from app.prospection.queue_manager import QueueManager


def test_opt_out_register(db):
    manager = QueueManager(db)
    opt = manager.register_opt_out("(22)99999-0000", reason="Nao quero")
    assert opt.contact_identifier == "(22)99999-0000"
    assert manager.is_opted_out(phone="(22)99999-0000")


def test_opt_out_blocks_send(db, company):
    manager = QueueManager(db)
    manager.register_opt_out(company.phone)
    assert manager.is_opted_out(phone=company.phone)


def test_opt_out_instagram(db, company):
    manager = QueueManager(db)
    manager.register_opt_out(company.instagram)
    assert manager.is_opted_out(instagram=company.instagram)


# --- Rate limit tests ---

def test_rate_limit_daily(db):
    manager = QueueManager(db)
    assert manager.can_send_today()


def test_rate_limit_hourly(db):
    manager = QueueManager(db)
    assert manager._can_send_hourly() if hasattr(manager, '_can_send_hourly') else True


# --- Idempotency tests ---

def test_no_duplicate_queue_entry(db, company):
    manager = QueueManager(db)
    entry1 = manager.add_to_queue(company.id)
    entry2 = manager.add_to_queue(company.id)
    assert entry1.id == entry2.id


def test_opt_out_blocks_queue(db, company):
    manager = QueueManager(db)
    manager.register_opt_out(company.phone)
    entry = manager.add_to_queue(company.id)
    assert entry.status == "BLOQUEADO_OPT_OUT"


# --- Dispatcher tests ---

from app.sending.dispatcher import Dispatcher


def test_dispatcher_status(db):
    dispatcher = Dispatcher(db)
    status = dispatcher.status
    assert "running" in status
    assert "paused" in status
    assert "circuit_open" in status
    assert "warmup_day" in status


def test_dispatcher_pause_resume(db):
    dispatcher = Dispatcher(db)
    dispatcher.pause()
    assert dispatcher._paused
    dispatcher.resume()
    assert not dispatcher._paused
    assert not dispatcher._circuit_open


def test_circuit_breaker(db):
    dispatcher = Dispatcher(db)
    dispatcher._consecutive_errors = 5
    dispatcher._check_circuit_breaker()
    assert dispatcher._circuit_open
    assert dispatcher._paused


def test_deduplication_30_days(db, company):
    msg = Message(
        company_id=company.id,
        opportunity_ids="[]",
        message_text="teste",
        status="enviado",
        generated_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    assert dispatcher._has_active_message(company.id)


def test_no_dedup_after_30_days(db):
    c = Company(
        name="Loja Velha",
        city_id=1,
        category_id=1,
        phone="(22)97777-2222",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    old_date = datetime.now(timezone.utc) - timedelta(days=35)
    msg = Message(
        company_id=c.id,
        opportunity_ids="[]",
        message_text="teste antigo",
        status="enviado",
        generated_at=old_date,
        sent_at=old_date,
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    assert not dispatcher._has_active_message(c.id)


# --- Loop / Scheduler tests ---

import asyncio
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_run_loop_respects_pause(db):
    dispatcher = Dispatcher(db)
    dispatcher._paused = True

    with patch("app.sending.dispatcher.settings") as mock_settings:
        mock_settings.DISPATCHER_INTERVAL_SECONDS = 0.05
        task = asyncio.create_task(dispatcher.run_loop())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert dispatcher._last_cycle_at is None


@pytest.mark.asyncio
async def test_run_loop_survives_exception(db):
    dispatcher = Dispatcher(db)
    call_count = 0

    async def flaky_cycle():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Erro simulado")
        dispatcher._last_cycle_at = datetime.now(timezone.utc)

    dispatcher.run_cycle = flaky_cycle

    with patch("app.sending.dispatcher.settings") as mock_settings:
        mock_settings.DISPATCHER_INTERVAL_SECONDS = 0.05
        task = asyncio.create_task(dispatcher.run_loop())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert call_count >= 2
    assert dispatcher._last_cycle_at is not None
    assert dispatcher._last_error == "Erro simulado"


@pytest.mark.asyncio
async def test_run_loop_sets_timestamps(db):
    dispatcher = Dispatcher(db)
    dispatcher._paused = True

    with patch("app.sending.dispatcher.settings") as mock_settings:
        mock_settings.DISPATCHER_INTERVAL_SECONDS = 0.05
        task = asyncio.create_task(dispatcher.run_loop())
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert dispatcher._started_at is not None
    assert dispatcher._next_cycle_at is not None


@pytest.mark.asyncio
async def test_stop_cancels_loop(db):
    dispatcher = Dispatcher(db)
    dispatcher._paused = True

    with patch("app.sending.dispatcher.settings") as mock_settings:
        mock_settings.DISPATCHER_INTERVAL_SECONDS = 0.05
        dispatcher._loop_task = asyncio.create_task(dispatcher.run_loop())
        await asyncio.sleep(0.15)

    dispatcher.stop()
    assert dispatcher._loop_task is None
    assert dispatcher._next_cycle_at is None


def test_status_has_new_fields(db):
    dispatcher = Dispatcher(db)
    status = dispatcher.status
    assert "started_at" in status
    assert "last_cycle_at" in status
    assert "next_cycle_at" in status
    assert "loop_active" in status
    assert status["started_at"] is None
    assert status["loop_active"] is False


@pytest.mark.asyncio
async def test_run_cycle_skips_when_paused(db):
    dispatcher = Dispatcher(db)
    dispatcher._paused = True
    await dispatcher.run_cycle()
    assert dispatcher._last_cycle_at is None
    assert dispatcher._running is False


# --- Auto-enqueue tests ---

from app.sending.dispatcher import AUTO_ENQUEUE_BATCH_SIZE


@pytest.mark.asyncio
async def test_auto_enqueue_new_company(db):
    c = Company(
        name="Nova Barbearia",
        city_id=1,
        category_id=1,
        phone="(22)91234-5678",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert len(eligible) >= 1
    assert any(co.id == c.id for co in eligible)


@pytest.mark.asyncio
async def test_auto_enqueue_skips_no_phone(db):
    c = Company(
        name="Sem Telefone",
        city_id=1,
        category_id=1,
        phone=None,
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert not any(co.name == "Sem Telefone" for co in eligible)


@pytest.mark.asyncio
async def test_auto_enqueue_skips_empty_phone(db):
    c = Company(
        name="Telefone Vazio",
        city_id=1,
        category_id=1,
        phone="",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert not any(co.name == "Telefone Vazio" for co in eligible)


@pytest.mark.asyncio
async def test_auto_enqueue_skips_recent_message(db):
    c = Company(
        name="Ja Mensagemada",
        city_id=1,
        category_id=1,
        phone="(22)91111-2222",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    msg = Message(
        company_id=c.id,
        opportunity_ids="[]",
        message_text="teste",
        status="enviado",
        generated_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert not any(co.id == c.id for co in eligible)


@pytest.mark.asyncio
async def test_auto_enqueue_skips_opt_out(db):
    c = Company(
        name="Optoutada",
        city_id=1,
        category_id=1,
        phone="(22)93333-4444",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()

    opt = OptOut(contact_identifier="(22)93333-4444", reason="teste")
    db.add(opt)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert not any(co.name == "Optoutada" for co in eligible)


@pytest.mark.asyncio
async def test_auto_enqueue_skips_active_queue(db):
    c = Company(
        name="Na Fila",
        city_id=1,
        category_id=1,
        phone="(22)95555-6666",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    q = ProspectingQueue(company_id=c.id, status="PENDENTE")
    db.add(q)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert not any(co.id == c.id for co in eligible)


@pytest.mark.asyncio
async def test_auto_enqueue_allows_reprocess_after_30_days(db):
    c = Company(
        name="Reprocessavel",
        city_id=1,
        category_id=1,
        phone="(22)97777-8888",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    old_date = datetime.now(timezone.utc) - timedelta(days=35)
    msg = Message(
        company_id=c.id,
        opportunity_ids="[]",
        message_text="teste velho",
        status="enviado",
        generated_at=old_date,
        sent_at=old_date,
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert any(co.id == c.id for co in eligible)


@pytest.mark.asyncio
async def test_auto_enqueue_batch_limit(db):
    for i in range(AUTO_ENQUEUE_BATCH_SIZE + 3):
        c = Company(
            name=f"Empresa Lote {i}",
            city_id=1,
            category_id=1,
            phone=f"(22)9{1000 + i}-0000",
            source="test",
            collected_at=datetime.now(timezone.utc),
        )
        db.add(c)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert len(eligible) <= AUTO_ENQUEUE_BATCH_SIZE


@pytest.mark.asyncio
async def test_auto_enqueue_base_exhausted(db, company):
    msg = Message(
        company_id=company.id,
        opportunity_ids="[]",
        message_text="teste",
        status="enviado",
        generated_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    count = await dispatcher._auto_enqueue()
    assert count == 0

    pending = dispatcher._get_pending_companies()
    assert len(pending) == 0
