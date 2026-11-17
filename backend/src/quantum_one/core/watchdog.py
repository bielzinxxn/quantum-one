"""Watchdog em thread separada: se o event loop parar de "bater", o processo é encerrado.

O Docker não reinicia contêiner apenas `unhealthy`; ele reinicia contêiner que SAIU.
Por isso um loop travado precisa derrubar o próprio processo para `restart:` agir.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable

EXIT_CODE_WATCHDOG = 70


class Watchdog:
    def __init__(
        self,
        seconds_since_tick: Callable[[], float],
        timeout_s: float,
        poll_s: float = 1.0,
        on_timeout: Callable[[], None] | None = None,
    ) -> None:
        self._seconds_since_tick = seconds_since_tick
        self._timeout_s = timeout_s
        self._poll_s = poll_s
        self._on_timeout = on_timeout or _hard_exit
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="watchdog", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._poll_s * 2)

    def _run(self) -> None:
        while not self._stop.wait(self._poll_s):
            if self._seconds_since_tick() > self._timeout_s:
                self._on_timeout()
                return


def _hard_exit() -> None:
    # stdout direto: o logger pode depender do loop travado
    sys.stdout.write('{"level":"critical","event":"watchdog_timeout_exiting"}\n')
    sys.stdout.flush()
    os._exit(EXIT_CODE_WATCHDOG)
