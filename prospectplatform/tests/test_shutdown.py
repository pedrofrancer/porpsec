import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import asyncio
from unittest.mock import patch

import pytest

from app.core.background import StopSignal, graceful_stop
from app.sending.dispatcher import Dispatcher


@pytest.mark.asyncio
async def test_stop_signal_wakes_sleeper():
    signal = StopSignal()
    asyncio.get_running_loop().call_later(0.05, signal.request)
    assert await signal.sleep(10) is True
    assert await StopSignal().sleep(0.01) is False


@pytest.mark.asyncio
async def test_shutdown_lets_current_send_finish():
    dispatcher = Dispatcher(None)
    events = []

    async def slow_cycle():
        events.append("inicio")
        await asyncio.sleep(0.2)  # envio em andamento
        events.append("gravado")

    dispatcher.run_cycle = slow_cycle
    with patch("app.sending.dispatcher.settings") as s:
        s.DISPATCHER_INTERVAL_SECONDS = 0.01
        dispatcher._loop_task = asyncio.create_task(dispatcher.run_loop())
        while not events:
            await asyncio.sleep(0.01)
        await dispatcher.shutdown()

    assert events == ["inicio", "gravado"]  # terminou o envio e nao comecou outro
    assert dispatcher._loop_task is None


@pytest.mark.asyncio
async def test_graceful_stop_cancels_after_timeout():
    signal = StopSignal()

    async def stuck():
        await asyncio.sleep(10)

    task = asyncio.create_task(stuck())
    await graceful_stop(task, signal, "teste", timeout=0.05)
    assert task.cancelled()
