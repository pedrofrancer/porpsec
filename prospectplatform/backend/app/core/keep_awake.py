"""Impede o Windows de suspender enquanto o servidor roda (a leitura IMAP e o envio param no sleep).

Nao impede desligar a tela nem o desligamento manual; so o sleep automatico por inatividade.
"""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def _set(flags: int) -> bool:
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))


def enable() -> bool:
    ok = _set(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
    if ok:
        logger.info("PC nao vai suspender enquanto o servidor estiver rodando")
    return ok


def disable():
    _set(_ES_CONTINUOUS)
