"""Parada cooperativa dos loops de fundo.

Cancelar uma task no meio de um envio pode deixar o e-mail enviado sem o status gravado.
Aqui o loop so para entre unidades de trabalho: pede-se a parada, espera-se o ciclo atual
terminar (com limite) e so depois cancela.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

SHUTDOWN_TIMEOUT_SECONDS = 60


class StopSignal:
    def __init__(self):
        self._event = asyncio.Event()

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def request(self):
        self._event.set()

    async def sleep(self, seconds: float) -> bool:
        """Dorme ate `seconds` ou ate a parada ser pedida. True = parada pedida."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False


async def graceful_stop(task: asyncio.Task | None, signal: StopSignal, name: str,
                        timeout: float = SHUTDOWN_TIMEOUT_SECONDS):
    signal.request()
    if task is None or task.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        logger.info(f"{name}: parou depois de terminar o ciclo em andamento")
    except asyncio.TimeoutError:
        logger.warning(f"{name}: ciclo nao terminou em {timeout}s, cancelando")
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
