"""Medição do desvio de relógio local × servidor da exchange (ADR-008 §3)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ClockReading:
    offset_ms: float  # servidor − local (positivo = relógio local atrasado)
    rtt_ms: float

    def within(self, max_offset_ms: float) -> bool:
        return abs(self.offset_ms) <= max_offset_ms


async def measure_offset(
    fetch_server_ms: Callable[[], Awaitable[int]],
    local_ms: Callable[[], float] = lambda: time.time() * 1000,
    samples: int = 3,
) -> ClockReading:
    """Usa o ponto médio da requisição; fica com a amostra de menor RTT (mais confiável)."""
    best: ClockReading | None = None
    for _ in range(max(1, samples)):
        start = local_ms()
        server = await fetch_server_ms()
        end = local_ms()
        reading = ClockReading(offset_ms=server - (start + end) / 2, rtt_ms=end - start)
        if best is None or reading.rtt_ms < best.rtt_ms:
            best = reading
    assert best is not None
    return best
