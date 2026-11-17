from __future__ import annotations

import threading
import time

from quantum_one.core.watchdog import Watchdog


def test_fires_when_loop_stops_ticking() -> None:
    fired = threading.Event()
    wd = Watchdog(lambda: 999.0, timeout_s=1.0, poll_s=0.01, on_timeout=fired.set)
    wd.start()
    assert fired.wait(1.0)
    wd.stop()


def test_does_not_fire_while_ticking() -> None:
    fired = threading.Event()
    wd = Watchdog(lambda: 0.0, timeout_s=1.0, poll_s=0.01, on_timeout=fired.set)
    wd.start()
    time.sleep(0.1)
    wd.stop()
    assert not fired.is_set()
