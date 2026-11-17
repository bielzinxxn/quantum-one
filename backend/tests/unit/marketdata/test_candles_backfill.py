from __future__ import annotations

from decimal import Decimal as D

import pytest

from quantum_one.marketdata.backfill import fetch_closed
from quantum_one.marketdata.candles import CandleSeries
from quantum_one.marketdata.models import Candle

M = 60_000
T0 = 1_700_000_040_000  # múltiplo de 60 s


def candle(t: int, close: str = "100", symbol: str = "BTCUSDT") -> Candle:
    p = D(close)
    return Candle(symbol, t, t + M - 1, p, p, p, p, D("1"), D("100"), 5)


def test_add_keeps_order_and_dedupes() -> None:
    s = CandleSeries("BTCUSDT")
    assert s.add(candle(T0 + 2 * M))
    assert s.add(candle(T0))
    assert s.add(candle(T0 + M))
    assert not s.add(candle(T0 + M, "101"))  # duplicata: atualiza, não é nova
    assert [c.open_time_ms for c in s.candles()] == [T0, T0 + M, T0 + 2 * M]
    assert s.closes()[1] == 101.0
    assert s.internal_gaps() == 0


def test_maxlen_trims_oldest_and_rejects_too_old() -> None:
    s = CandleSeries("BTCUSDT", maxlen=3)
    for i in range(5):
        s.add(candle(T0 + i * M))
    assert len(s) == 3 and s.candles()[0].open_time_ms == T0 + 2 * M
    assert not s.add(candle(T0))


def test_gap_detection() -> None:
    s = CandleSeries("BTCUSDT")
    assert s.gap_after_last(T0) is None  # série vazia
    s.add(candle(T0))
    assert s.gap_after_last(T0 + M) is None
    assert s.gap_after_last(T0 + 4 * M) == (T0 + M, T0 + 4 * M)
    s.add(candle(T0 + 4 * M))
    assert s.internal_gaps() == 3


def test_wrong_symbol_rejected() -> None:
    with pytest.raises(ValueError, match="ETHUSDT"):
        CandleSeries("BTCUSDT").add(candle(T0, symbol="ETHUSDT"))


class FakeSource:
    def __init__(self, now: int, per_call: int = 1000) -> None:
        self.now, self.per_call, self.calls = now, per_call, 0

    async def klines(
        self, symbol: str, interval: str, start_ms: int, end_ms: int | None, limit: int
    ) -> list[Candle]:
        self.calls += 1
        out, t = [], start_ms
        stop = min(end_ms if end_ms is not None else self.now, self.now)
        while t <= stop and len(out) < min(limit, self.per_call):
            out.append(candle(t))
            t += M
        return out


async def test_fetch_closed_excludes_in_progress_candle() -> None:
    now = T0 + 5 * M + 30_000  # meio da 6ª vela
    got = await fetch_closed(FakeSource(now), "BTCUSDT", T0, T0 + 10 * M, now)
    assert [c.open_time_ms for c in got] == [T0 + i * M for i in range(5)]


async def test_fetch_closed_paginates_until_end() -> None:
    now = T0 + 3000 * M
    src = FakeSource(now, per_call=1000)
    got = await fetch_closed(src, "BTCUSDT", T0, T0 + 2500 * M, now)
    assert len(got) == 2500 and src.calls == 3
    assert got[-1].open_time_ms == T0 + 2499 * M


async def test_fetch_closed_respects_max_calls() -> None:
    now = T0 + 9000 * M
    src = FakeSource(now)
    got = await fetch_closed(src, "BTCUSDT", T0, T0 + 9000 * M, now, max_calls=2)
    assert len(got) == 2000 and src.calls == 2
