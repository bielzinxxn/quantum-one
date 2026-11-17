from __future__ import annotations

import dataclasses
from decimal import Decimal as D

from quantum_one.exchange.binance.filters import parse_instrument
from quantum_one.marketdata.models import BookTop, Candle, Depth, KlineUpdate
from quantum_one.marketdata.scanner import ScannerState, Thresholds
from quantum_one.marketdata.universe import UniverseRules, select_universe
from tests.fakes.binance_payloads import BTCUSDT

BASE = parse_instrument(BTCUSDT)
M = 60_000
T0 = 1_700_000_040_000


def inst(symbol: str, base: str, quote: str = "USDT", status: str = "TRADING"):  # type: ignore[no-untyped-def]
    return dataclasses.replace(BASE, symbol=symbol, base=base, quote=quote, status=status)


INSTRUMENTS = [
    inst("BTCUSDT", "BTC"),
    inst("ETHUSDT", "ETH"),
    inst("SOLUSDT", "SOL"),
    inst("USDCUSDT", "USDC"),
    inst("ETHBTC", "ETH", quote="BTC"),
    inst("LUNAUSDT", "LUNA", status="BREAK"),
    inst("DOGEUSDT", "DOGE"),
    inst("XRPUSDT", "XRP"),
]
VOLUMES = {
    "BTCUSDT": 9e9,
    "ETHUSDT": 5e9,
    "USDCUSDT": 8e9,
    "SOLUSDT": 1e9,
    "ETHBTC": 9e9,
    "LUNAUSDT": 9e9,
    "DOGEUSDT": 1e6,
    "XRPUSDT": 1e9,
}
RULES = UniverseRules(3, 5e6, (), frozenset({"USDC"}))


def test_universe_ranking_and_exclusions() -> None:
    # USDC (stable) excluído; ETHBTC não é USDT; LUNA não negocia; DOGE abaixo do mínimo
    # SOL e XRP empatam em volume → desempate alfabético
    assert select_universe(INSTRUMENTS, VOLUMES, RULES) == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def test_extras_always_included_if_tradable() -> None:
    rules = dataclasses.replace(RULES, size=1, extra_symbols=("DOGEUSDT", "LUNAUSDT", "NOPEUSDT"))
    assert select_universe(INSTRUMENTS, VOLUMES, rules) == ["BTCUSDT", "DOGEUSDT"]


def test_universe_is_deterministic() -> None:
    assert select_universe(reversed(INSTRUMENTS), VOLUMES, RULES) == select_universe(
        INSTRUMENTS, VOLUMES, RULES
    )


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def c(t: int, close: float, qv: float = 100.0) -> Candle:
    p = D(str(close))
    return Candle("BTCUSDT", t, t + M - 1, p, p, p, p, D(1), D(str(qv)), 1)


def _state(clock: Clock) -> ScannerState:
    s = ScannerState(
        stale_after_s=10, probe_quote=100, thresholds=Thresholds(min_history=60), clock=clock
    )
    s.set_universe(["BTCUSDT"])
    s.connected = True
    return s


def test_stale_until_data_and_after_silence_or_disconnect() -> None:
    clock = Clock()
    s = _state(clock)
    assert s.snapshot("BTCUSDT").stale  # nenhum dado ainda
    s.on_kline(KlineUpdate(c(T0, 100), closed=False))
    assert not s.snapshot("BTCUSDT").stale
    clock.t += 11
    snap = s.snapshot("BTCUSDT")
    assert snap.stale and "stale" in snap.flags and snap.data_age_s == 11
    s.on_depth(Depth("BTCUSDT", ((99.0, 1.0),), ((101.0, 1.0),)))
    assert not s.snapshot("BTCUSDT").stale
    s.connected = False
    assert s.snapshot("BTCUSDT").stale


def test_kline_gap_and_backfill() -> None:
    s = _state(Clock())
    candle, gap = s.on_kline(KlineUpdate(c(T0, 100), closed=True))
    assert candle is not None and gap is None
    candle, gap = s.on_kline(KlineUpdate(c(T0 + 3 * M, 100), closed=True))
    assert gap is not None and (gap.start_ms, gap.end_ms) == (T0 + M, T0 + 3 * M)
    new = s.add_backfill("BTCUSDT", [c(T0 + 2 * M, 100), c(T0 + M, 100), c(T0, 100)])
    assert [x.open_time_ms for x in new] == [T0 + M, T0 + 2 * M]  # T0 já existia
    assert s.series("BTCUSDT").internal_gaps() == 0
    assert s.add_backfill("XXX", [c(T0, 1)]) == []
    assert s.on_kline(KlineUpdate(dataclasses.replace(c(T0, 1), symbol="XXX"), True)) == (
        None,
        None,
    )


def test_flags_abnormal_move_volume_spike_wide_spread_thin_book() -> None:
    s = _state(Clock())
    price = 100.0
    for i in range(70):
        price *= 1.001 if i % 2 == 0 else 1 / 1.001
        s.on_kline(KlineUpdate(c(T0 + i * M, round(price, 6), 100.0), closed=True))
    s.on_kline(KlineUpdate(c(T0 + 70 * M, round(price * 1.03, 6), 2000.0), closed=True))
    s.on_book(BookTop("BTCUSDT", 99.0, 1.0, 101.0, 1.0))  # spread 200 bps
    s.on_depth(Depth("BTCUSDT", ((99.0, 1.0), (90.0, 1.0)), ((101.0, 1.0), (110.0, 1.0))))
    snap = s.snapshot("BTCUSDT")
    assert {"abnormal_move", "volume_spike", "wide_spread", "thin_book"} <= set(snap.flags)
    assert "insufficient_history" not in snap.flags
    assert snap.rel_volume_1m == 20.0
    assert snap.candles == 71 and snap.last_close is not None
    assert snap.ret_60m is not None and snap.realized_vol_1h is not None


def test_insufficient_depth_for_probe_flag() -> None:
    s = ScannerState(10, probe_quote=1e9, clock=Clock())
    s.set_universe(["BTCUSDT"])
    s.on_book(BookTop("BTCUSDT", 99.0, 1.0, 101.0, 1.0))
    s.on_depth(Depth("BTCUSDT", ((99.0, 1.0),), ((101.0, 1.0),)))
    snap = s.snapshot("BTCUSDT")
    assert snap.slippage_buy_bps is None
    assert "insufficient_depth_for_probe" in snap.flags


def test_set_universe_preserves_history() -> None:
    s = _state(Clock())
    s.on_kline(KlineUpdate(c(T0, 100), closed=True))
    assert s.set_universe(["BTCUSDT", "ETHUSDT"])
    assert len(s.series("BTCUSDT")) == 1
    assert not s.set_universe(["BTCUSDT", "ETHUSDT"])
    tick = s.tick()
    assert tick.universe == ["BTCUSDT", "ETHUSDT"] and len(tick.symbols) == 2
