"""Preenchimento de lacunas por REST (GET /api/v3/klines, máx. 1000 por chamada)."""

from __future__ import annotations

from typing import Protocol

from quantum_one.marketdata.models import ONE_MINUTE_MS, Candle

MAX_KLINES_PER_CALL = 1000


class KlineSource(Protocol):
    async def klines(
        self, symbol: str, interval: str, start_ms: int, end_ms: int | None, limit: int
    ) -> list[Candle]: ...


async def fetch_closed(
    source: KlineSource, symbol: str, start_ms: int, end_ms: int, now_ms: int, max_calls: int = 5
) -> list[Candle]:
    """Velas 1m FECHADAS com open_time em [start_ms, end_ms).

    O REST devolve a vela em andamento como última: descartada se close_time >= now_ms.
    """
    out: list[Candle] = []
    cursor = start_ms
    for _ in range(max_calls):
        if cursor >= end_ms:
            break
        batch = await source.klines(symbol, "1m", cursor, end_ms - 1, MAX_KLINES_PER_CALL)
        if not batch:
            break
        out.extend(c for c in batch if c.close_time_ms < now_ms and c.open_time_ms < end_ms)
        last = batch[-1].open_time_ms
        if len(batch) < MAX_KLINES_PER_CALL or last + ONE_MINUTE_MS <= cursor:
            break
        cursor = last + ONE_MINUTE_MS
    return out
