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


@pytest.mark.asyncio
async def test_auto_enqueue_runs_outside_send_window(db):
    c = Company(
        name="Fora Horario",
        city_id=1,
        category_id=1,
        phone="(22)94444-5555",
        source="test",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    dispatcher = Dispatcher(db)

    with patch.object(dispatcher, "_is_within_send_window", return_value=False), \
         patch.object(dispatcher, "_auto_enqueue", new_callable=AsyncMock) as mock_enqueue:
        mock_enqueue.return_value = 1
        await dispatcher.run_cycle()

    mock_enqueue.assert_called_once()
    assert dispatcher._last_cycle_at is not None
    assert dispatcher._running is False


# --- CollectionTracker tests ---

from app.sending.dispatcher import CollectionTracker, COLLECTION_COOLDOWN_DAYS


def test_collection_tracker_get_targets():
    targets = CollectionTracker.get_targets()
    assert isinstance(targets, list)
    assert len(targets) > 0
    assert "category_slug" in targets[0]
    assert "city_name" in targets[0]


def test_collection_tracker_get_next_target_no_history():
    CollectionTracker.HISTORY_FILE = CollectionTracker.HISTORY_FILE.parent / "test_collection_history.json"
    if CollectionTracker.HISTORY_FILE.exists():
        CollectionTracker.HISTORY_FILE.unlink()

    target = CollectionTracker.get_next_target()
    assert target is not None
    assert "category_slug" in target
    assert "city_name" in target

    CollectionTracker.HISTORY_FILE.unlink(missing_ok=True)


def test_collection_tracker_records_and_rotates():
    CollectionTracker.HISTORY_FILE = CollectionTracker.HISTORY_FILE.parent / "test_collection_history.json"
    if CollectionTracker.HISTORY_FILE.exists():
        CollectionTracker.HISTORY_FILE.unlink()

    targets = CollectionTracker.get_targets()
    first_target = targets[0]
    CollectionTracker.record_run(
        first_target["category_slug"],
        first_target["city_name"],
        {"imported": 5},
    )

    next_target = CollectionTracker.get_next_target()
    assert next_target is not None
    if len(targets) > 1:
        assert f"{next_target['category_slug']}:{next_target['city_name']}" != \
               f"{first_target['category_slug']}:{first_target['city_name']}"

    CollectionTracker.HISTORY_FILE.unlink(missing_ok=True)


def test_collection_tracker_all_used_returns_none():
    CollectionTracker.HISTORY_FILE = CollectionTracker.HISTORY_FILE.parent / "test_collection_history.json"
    if CollectionTracker.HISTORY_FILE.exists():
        CollectionTracker.HISTORY_FILE.unlink()

    targets = CollectionTracker.get_targets()
    for t in targets:
        CollectionTracker.record_run(t["category_slug"], t["city_name"], {"imported": 1})

    result = CollectionTracker.get_next_target()
    assert result is None

    CollectionTracker.HISTORY_FILE.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_try_auto_collect_no_targets(db):
    CollectionTracker.HISTORY_FILE = CollectionTracker.HISTORY_FILE.parent / "test_collection_history.json"
    if CollectionTracker.HISTORY_FILE.exists():
        CollectionTracker.HISTORY_FILE.unlink()

    targets = CollectionTracker.get_targets()
    for t in targets:
        CollectionTracker.record_run(t["category_slug"], t["city_name"], {"imported": 1})

    dispatcher = Dispatcher(db)
    count = await dispatcher._try_auto_collect()
    assert count == 0

    CollectionTracker.HISTORY_FILE.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_try_auto_collect_runs_when_base_exhausted(db):
    CollectionTracker.HISTORY_FILE = CollectionTracker.HISTORY_FILE.parent / "test_collection_history.json"
    if CollectionTracker.HISTORY_FILE.exists():
        CollectionTracker.HISTORY_FILE.unlink()

    dispatcher = Dispatcher(db)

    with patch.object(dispatcher, "_run_auto_collection", new_callable=AsyncMock) as mock_collect:
        mock_collect.return_value = 3
        count = await dispatcher._try_auto_collect()
        assert count == 3
        mock_collect.assert_called_once()

    CollectionTracker.HISTORY_FILE.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_run_cycle_triggers_collection_on_exhausted_base(db):
    CollectionTracker.HISTORY_FILE = CollectionTracker.HISTORY_FILE.parent / "test_collection_history.json"
    if CollectionTracker.HISTORY_FILE.exists():
        CollectionTracker.HISTORY_FILE.unlink()

    dispatcher = Dispatcher(db)

    with patch.object(dispatcher, "_auto_enqueue", new_callable=AsyncMock) as mock_enqueue, \
         patch.object(dispatcher, "_try_auto_collect", new_callable=AsyncMock) as mock_collect, \
         patch.object(dispatcher, "_is_within_send_window", return_value=False):

        mock_enqueue.side_effect = [0, 1]
        mock_collect.return_value = 3

        await dispatcher.run_cycle()

    mock_collect.assert_called_once()
    assert mock_enqueue.call_count == 2

    CollectionTracker.HISTORY_FILE.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_run_cycle_skips_collection_when_eligible_exist(db):
    CollectionTracker.HISTORY_FILE = CollectionTracker.HISTORY_FILE.parent / "test_collection_history.json"
    if CollectionTracker.HISTORY_FILE.exists():
        CollectionTracker.HISTORY_FILE.unlink()

    dispatcher = Dispatcher(db)

    with patch.object(dispatcher, "_auto_enqueue", new_callable=AsyncMock) as mock_enqueue, \
         patch.object(dispatcher, "_try_auto_collect", new_callable=AsyncMock) as mock_collect, \
         patch.object(dispatcher, "_is_within_send_window", return_value=False):

        mock_enqueue.return_value = 2
        await dispatcher.run_cycle()

    mock_collect.assert_not_called()

    CollectionTracker.HISTORY_FILE.unlink(missing_ok=True)


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


# --- Bug 1 fix: aprovado MUST NOT block process_company ---

def test_aprovado_does_not_block_has_active_message(db, company):
    msg = Message(
        company_id=company.id,
        opportunity_ids="[]",
        message_text="teste aprovado",
        status="aprovado",
        generated_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    assert not dispatcher._has_active_message(company.id)


def test_enviado_blocks_has_active_message(db, company):
    msg = Message(
        company_id=company.id,
        opportunity_ids="[]",
        message_text="teste enviado",
        status="enviado",
        generated_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    assert dispatcher._has_active_message(company.id)


def test_rascunho_does_not_block_has_active_message(db, company):
    msg = Message(
        company_id=company.id,
        opportunity_ids="[]",
        message_text="teste rascunho",
        status="rascunho",
        generated_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    assert not dispatcher._has_active_message(company.id)


def test_aprovado_does_not_exclude_from_eligible(db, company):
    msg = Message(
        company_id=company.id,
        opportunity_ids="[]",
        message_text="teste aprovado eligible",
        status="aprovado",
        generated_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    dispatcher = Dispatcher(db)
    eligible = dispatcher._get_eligible_companies()
    assert any(co.id == company.id for co in eligible)


# --- Bug 3 fix: send window uses BRT ---

from app.sending.dispatcher import BRT
from unittest.mock import patch


def test_send_window_uses_brt_not_utc():
    from app.sending.dispatcher import Dispatcher
    from app.core.config import settings

    dispatcher = Dispatcher.__new__(Dispatcher)

    brt_noon = datetime(2026, 8, 21, 12, 0, 0, tzinfo=BRT)
    with patch("app.sending.dispatcher.datetime") as mock_dt:
        mock_dt.now.return_value = brt_noon
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert dispatcher._is_within_send_window()


def test_send_window_rejects_outside_brt_hours():
    from app.sending.dispatcher import Dispatcher

    dispatcher = Dispatcher.__new__(Dispatcher)

    brt_20h = datetime(2026, 8, 21, 20, 0, 0, tzinfo=BRT)
    with patch("app.sending.dispatcher.datetime") as mock_dt:
        mock_dt.now.return_value = brt_20h
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert not dispatcher._is_within_send_window()


def test_send_window_9h_brt_is_inside():
    from app.sending.dispatcher import Dispatcher

    dispatcher = Dispatcher.__new__(Dispatcher)

    brt_9h = datetime(2026, 8, 21, 9, 0, 0, tzinfo=BRT)
    with patch("app.sending.dispatcher.datetime") as mock_dt:
        mock_dt.now.return_value = brt_9h
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert dispatcher._is_within_send_window()


def test_send_window_18h59_brt_is_inside():
    from app.sending.dispatcher import Dispatcher

    dispatcher = Dispatcher.__new__(Dispatcher)

    brt_1859 = datetime(2026, 8, 21, 18, 59, 0, tzinfo=BRT)
    with patch("app.sending.dispatcher.datetime") as mock_dt:
        mock_dt.now.return_value = brt_1859
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert dispatcher._is_within_send_window()


def test_send_window_utc_20_is_brt_17_inside():
    from app.sending.dispatcher import Dispatcher

    dispatcher = Dispatcher.__new__(Dispatcher)

    brt_17h = datetime(2026, 8, 21, 17, 0, 0, tzinfo=BRT)
    with patch("app.sending.dispatcher.datetime") as mock_dt:
        mock_dt.now.return_value = brt_17h
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert dispatcher._is_within_send_window()


# --- ContentValidator specificity tests ---

def test_validate_rejects_generic_no_specificity():
    ok, err = ContentValidator.validate(
        "Barbearia Teste e um otimo estabelecimento da regiao, recomendo.",
        "Barbearia Teste",
    )
    assert not ok
    assert "generica" in err.lower() or "especifico" in err.lower()


def test_validate_accepts_message_with_site_mention():
    ok, err = ContentValidator.validate(
        "Barbearia Teste, vi que voces nao tem site, so o Instagram. Isso faz falta pra quem pesquisa no Google.",
        "Barbearia Teste",
    )
    assert ok


def test_validate_accepts_message_with_instagram_mention():
    ok, err = ContentValidator.validate(
        "Barbearia Teste, notei que o Instagram ta sem postar faz tempo. Gente que procura pode achar o perfil parado.",
        "Barbearia Teste",
    )
    assert ok


def test_validate_accepts_message_with_nota_google():
    ok, err = ContentValidator.validate(
        "Barbearia Teste, seu Google ta com nota boa mas o perfil ta incompleto, falta horario.",
        "Barbearia Teste",
    )
    assert ok


def test_validate_rejects_just_company_name():
    ok, err = ContentValidator.validate(
        "Barbearia Teste e um otimo negocio da regiao.",
        "Barbearia Teste",
    )
    assert not ok
    assert "generica" in err.lower() or "especifico" in err.lower()


def test_validate_rejects_when_no_opp_mentioned():
    from app.models.opportunity import Opportunity

    opp = Opportunity(
        company_id=1,
        problem="sem agendamento online para clientes",
        suggested_solution="Sistema de Agendamento",
        priority="alta",
    )
    ok, err = ContentValidator.validate(
        "Barbearia Teste, vi que voces nao tem site. Topa eu te mostrar como ficaria?",
        "Barbearia Teste",
        opportunities=[opp],
    )
    assert not ok
    assert "oportunidade" in err.lower()
