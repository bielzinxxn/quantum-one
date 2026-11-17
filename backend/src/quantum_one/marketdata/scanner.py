"""Estado do scanner: velas, livro e frescor por símbolo → snapshots com métricas e flags."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from quantum_one.contracts.market import ScannerTick, SymbolSnapshot
from quantum_one.marketdata import metrics as m
from quantum_one.marketdata.candles import CandleSeries
from quantum_one.marketdata.models import BookTop, Candle, Depth, KlineUpdate


@dataclass(frozen=True)
class Thresholds:
    abnormal_z: float = 4.0
    volume_spike: float = 5.0
    wide_spread_bps: float = 25.0
    thin_depth_quote_1pct: float = 50_000.0
    min_history: int = 60


@dataclass(frozen=True)
class Gap:
    symbol: str
    start_ms: int
    end_ms: int  # exclusivo


@dataclass
class SymbolState:
    series: CandleSeries
    book: BookTop | None = None
    depth: Depth | None = None
    last_data_at: float | None = None
    last_book_at: float | None = None
    pending_gaps: list[Gap] = field(default_factory=list)


class ScannerState:
    def __init__(
        self,
        stale_after_s: float,
        probe_quote: float,
        thresholds: Thresholds | None = None,
        maxlen: int = 1440,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._stale_after = stale_after_s
        self._probe = probe_quote
        self._th = thresholds or Thresholds()
        self._maxlen = maxlen
        self._clock = clock
        self._symbols: dict[str, SymbolState] = {}
        self.connected = False

    @property
    def universe(self) -> list[str]:
        return list(self._symbols)

    def set_universe(self, symbols: Iterable[str]) -> bool:
        """Atualiza o universo preservando o histórico dos que continuam. True se mudou."""
        wanted = list(dict.fromkeys(symbols))
        if wanted == list(self._symbols):
            return False
        self._symbols = {
            s: self._symbols.get(s) or SymbolState(CandleSeries(s, self._maxlen)) for s in wanted
        }
        return True

    def series(self, symbol: str) -> CandleSeries:
        return self._symbols[symbol].series

    def on_kline(self, update: KlineUpdate) -> tuple[Candle | None, Gap | None]:
        st = self._symbols.get(update.candle.symbol)
        if st is None:
            return None, None
        st.last_data_at = self._clock()
        if not update.closed:
            return None, None
        gap_range = st.series.gap_after_last(update.candle.open_time_ms)
        gap = Gap(update.candle.symbol, *gap_range) if gap_range else None
        is_new = st.series.add(update.candle)
        return (update.candle if is_new else None), gap

    def on_book(self, top: BookTop) -> None:
        st = self._symbols.get(top.symbol)
        if st is not None:
            st.book, st.last_book_at = top, self._clock()

    def on_depth(self, depth: Depth) -> None:
        st = self._symbols.get(depth.symbol)
        if st is not None:
            now = self._clock()
            st.depth, st.last_book_at, st.last_data_at = depth, now, now

    def add_backfill(self, symbol: str, candles: Iterable[Candle]) -> list[Candle]:
        st = self._symbols.get(symbol)
        if st is None:
            return []
        return [c for c in sorted(candles, key=lambda c: c.open_time_ms) if st.series.add(c)]

    def _age(self, t: float | None) -> float | None:
        return None if t is None else round(self._clock() - t, 3)

    def snapshot(self, symbol: str) -> SymbolSnapshot:
        st = self._symbols[symbol]
        data_age, book_age = self._age(st.last_data_at), self._age(st.last_book_at)
        stale = not self.connected or data_age is None or data_age > self._stale_after
        closes, volumes = st.series.closes(), st.series.quote_volumes()
        candles = st.series.candles()

        bid = ask = spread = None
        d05b = d05a = d1b = d1a = slip_b = slip_s = None
        truncated = False
        if st.book is not None:
            bid, ask = st.book.bid, st.book.ask
            spread = m.spread_bps(bid, ask)
        mid_price = m.mid(bid, ask) if bid is not None and ask is not None else None
        if st.depth is not None and mid_price:
            d05b, t1 = m.depth_within(st.depth.bids, mid_price, 0.5, "bid")
            d05a, t2 = m.depth_within(st.depth.asks, mid_price, 0.5, "ask")
            d1b, t3 = m.depth_within(st.depth.bids, mid_price, 1.0, "bid")
            d1a, t4 = m.depth_within(st.depth.asks, mid_price, 1.0, "ask")
            truncated = t1 or t2 or t3 or t4
            slip_b = m.slippage_bps(st.depth.asks, mid_price, self._probe, "buy")
            slip_s = m.slippage_bps(st.depth.bids, mid_price, self._probe, "sell")

        z = m.return_zscore(closes)
        rel_vol = m.relative_volume(volumes)
        flags: list[str] = []
        if stale:
            flags.append("stale")
        if len(closes) < self._th.min_history:
            flags.append("insufficient_history")
        if z is not None and abs(z) >= self._th.abnormal_z:
            flags.append("abnormal_move")
        if rel_vol is not None and rel_vol >= self._th.volume_spike:
            flags.append("volume_spike")
        if spread is not None and spread >= self._th.wide_spread_bps:
            flags.append("wide_spread")
        thin = (
            d1b is not None and d1a is not None and min(d1b, d1a) < self._th.thin_depth_quote_1pct
        )
        if thin and not truncated:
            flags.append("thin_book")
        if st.depth is not None and mid_price and (slip_b is None or slip_s is None):
            flags.append("insufficient_depth_for_probe")

        return SymbolSnapshot(
            symbol=symbol,
            stale=stale,
            data_age_s=data_age,
            book_age_s=book_age,
            last_close=candles[-1].close if candles else None,
            bid=bid,
            ask=ask,
            spread_bps=spread,
            depth_bid_quote_0_5pct=d05b,
            depth_ask_quote_0_5pct=d05a,
            depth_bid_quote_1pct=d1b,
            depth_ask_quote_1pct=d1a,
            depth_truncated=truncated,
            slippage_buy_bps=slip_b,
            slippage_sell_bps=slip_s,
            ret_5m=m.simple_return(closes, 5),
            ret_15m=m.simple_return(closes, 15),
            ret_60m=m.simple_return(closes, 60),
            return_z_1m=z,
            rel_volume_1m=rel_vol,
            realized_vol_1h=m.realized_vol(closes, 60),
            realized_vol_12h=m.realized_vol(closes, 720),
            candles=len(closes),
            flags=flags,
        )

    def tick(self) -> ScannerTick:
        return ScannerTick(
            at=datetime.now(tz=UTC),
            connected=self.connected,
            universe=self.universe,
            symbols=[self.snapshot(s) for s in self._symbols],
        )
