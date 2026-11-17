"""Market Scanner (Fase 4): stream → velas/livro → métricas → md:candles, md:scanner, md:health.

Tarefas concorrentes: consumo do stream, preenchimento de lacunas, publicação periódica
e atualização do universo. Uma falha inesperada derruba o processo (Docker reinicia).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from quantum_one.bus.publisher import StreamPublisher
from quantum_one.contracts.market import STREAM_CANDLES, STREAM_HEALTH, STREAM_SCANNER, CandleClosed
from quantum_one.core.logging import get_logger
from quantum_one.db import market as repo
from quantum_one.exchange.errors import classify
from quantum_one.marketdata.backfill import fetch_closed
from quantum_one.marketdata.connection import MarketStream
from quantum_one.marketdata.models import (
    ONE_MINUTE_MS,
    BookTop,
    Candle,
    Connected,
    Depth,
    Disconnected,
    KlineUpdate,
    StreamEvent,
)
from quantum_one.marketdata.scanner import Gap, ScannerState
from quantum_one.marketdata.streams import combined_url
from quantum_one.marketdata.universe import UniverseRules, select_universe
from quantum_one.services.runtime import ServiceContext, sleep_or_stop

PERSIST_SNAPSHOTS_EVERY_S = 60.0
RETRY_S = 30.0


class MarketRest(Protocol):
    async def klines(
        self, symbol: str, interval: str, start_ms: int, end_ms: int | None, limit: int
    ) -> list[Candle]: ...
    async def quote_volumes_24h(self) -> dict[str, float]: ...


class EventSource(Protocol):
    connected: bool
    reconnects: int
    unknown_messages: int

    def request_reconnect(self) -> None: ...
    def events(self, stop: asyncio.Event) -> AsyncIterator[StreamEvent]: ...


def _candle_event(c: Candle, backfill: bool) -> dict[str, Any]:
    payload = CandleClosed(
        symbol=c.symbol,
        timeframe=c.timeframe,
        open_time=repo.ms_to_dt(c.open_time_ms),
        open=c.open,
        high=c.high,
        low=c.low,
        close=c.close,
        volume=c.volume,
        quote_volume=c.quote_volume,
        trades=c.trades,
        backfill=backfill,
    )
    return payload.model_dump(mode="json")


class ScannerService:
    def __init__(
        self,
        ctx: ServiceContext,
        rest: MarketRest,
        stream_factory: Callable[[Callable[[], str]], EventSource] | None = None,
        now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        s = ctx.settings
        self.ctx, self.rest, self._now_ms = ctx, rest, now_ms
        self.state = ScannerState(s.scanner_stale_after_s, s.scanner_slippage_probe_quote)
        self.publisher = StreamPublisher(ctx.redis, "marketdata")
        self.rules = UniverseRules(
            s.scanner_universe_size, s.scanner_min_quote_volume, s.extra_symbols, s.excluded_bases
        )
        factory = stream_factory or (
            lambda url: MarketStream(url, s.scanner_stale_after_s, s.scanner_ws_rotate_after_s)
        )
        self.stream = factory(lambda: combined_url(s.ws_base_url, self.state.universe))
        self._gaps: asyncio.Queue[Gap | None] = asyncio.Queue()
        self.log = get_logger()

    # ---------- universo ----------
    async def refresh_universe(self) -> bool:
        instruments = await repo.load_tradable_instruments(self.ctx.pool, self.rules.quote)
        if not instruments:
            raise RuntimeError("instrumentos ainda não sincronizados")
        volumes = await self.rest.quote_volumes_24h()
        universe = select_universe(instruments, volumes, self.rules)
        if not universe:
            raise RuntimeError("universo vazio com as regras atuais")
        changed = self.state.set_universe(universe)
        if changed:
            self.log.info("scanner_universe", size=len(universe), symbols=universe)
        return changed

    async def _initial_universe(self) -> bool:
        while not self.ctx.stop.is_set():
            try:
                await self.refresh_universe()
                return True
            except Exception as exc:
                self.log.warning("scanner_universe_unavailable", error=str(exc)[:200])
                self._publish_status(error=str(exc)[:200])
                if await sleep_or_stop(self.ctx.stop, RETRY_S):
                    break
        return False

    async def _universe_loop(self) -> None:
        while not await sleep_or_stop(self.ctx.stop, self.ctx.settings.scanner_universe_refresh_s):
            try:
                if await self.refresh_universe():
                    self.stream.request_reconnect()
            except Exception as exc:
                self.log.warning("scanner_universe_refresh_failed", error=str(exc)[:200])

    # ---------- velas e lacunas ----------
    async def _store_candles(self, candles: list[Candle], backfill: bool) -> None:
        if not candles:
            return
        await repo.upsert_candles(self.ctx.pool, candles, "rest" if backfill else "stream")
        for c in candles:
            await self.publisher.publish(
                STREAM_CANDLES, "candle.closed", _candle_event(c, backfill)
            )

    def _schedule_full_backfill(self) -> None:
        now = self._now_ms()
        current_minute = now - now % ONE_MINUTE_MS
        warmup = self.ctx.settings.scanner_warmup_candles * ONE_MINUTE_MS
        for symbol in self.state.universe:
            last = self.state.series(symbol).last_open_time
            start = last + ONE_MINUTE_MS if last is not None else current_minute - warmup
            if start < current_minute:
                self._gaps.put_nowait(Gap(symbol, start, current_minute))

    async def _backfill_loop(self) -> None:
        while not self.ctx.stop.is_set():
            gap = await self._gaps.get()
            if gap is None:
                return
            if gap.symbol not in self.state.universe:
                continue
            try:
                fetched = await fetch_closed(
                    self.rest, gap.symbol, gap.start_ms, gap.end_ms, self._now_ms()
                )
                new = self.state.add_backfill(gap.symbol, fetched)
                await self._store_candles(new, backfill=True)
            except Exception as exc:
                err = classify(exc)
                self.log.warning("backfill_failed", symbol=gap.symbol, kind=err.kind.value)
                await sleep_or_stop(self.ctx.stop, 5.0)
                self._gaps.put_nowait(gap)  # tenta de novo; o stream continua

    # ---------- stream ----------
    async def _consume(self) -> None:
        async for event in self.stream.events(self.ctx.stop):
            if isinstance(event, KlineUpdate):
                candle, gap = self.state.on_kline(event)
                if gap is not None:
                    self._gaps.put_nowait(gap)
                if candle is not None:
                    await self._store_candles([candle], backfill=False)
            elif isinstance(event, BookTop):
                self.state.on_book(event)
            elif isinstance(event, Depth):
                self.state.on_depth(event)
            elif isinstance(event, Connected):
                self.state.connected = True
                self.log.info("market_stream_connected", symbols=len(self.state.universe))
                self._schedule_full_backfill()
            elif isinstance(event, Disconnected):
                self.state.connected = False
        self._gaps.put_nowait(None)

    # ---------- publicação ----------
    def _publish_status(self, **extra: Any) -> None:
        tick_universe = self.state.universe
        self.ctx.state.extra["scanner"] = {
            "connected": self.state.connected,
            "universe": len(tick_universe),
            "reconnects": self.stream.reconnects,
            "unknown_messages": self.stream.unknown_messages,
            **extra,
        }

    async def _publish_loop(self) -> None:
        last_persist = 0.0
        while not await sleep_or_stop(self.ctx.stop, self.ctx.settings.scanner_snapshot_interval_s):
            tick = self.state.tick()
            stale = [s.symbol for s in tick.symbols if s.stale]
            await self.publisher.publish(
                STREAM_SCANNER, "scanner.tick", tick.model_dump(mode="json")
            )
            await self.publisher.publish(
                STREAM_HEALTH,
                "market.health",
                {
                    "connected": tick.connected,
                    "symbols": {
                        s.symbol: {"stale": s.stale, "data_age_s": s.data_age_s}
                        for s in tick.symbols
                    },
                },
            )
            self._publish_status(stale=len(stale), last_tick=tick.at.isoformat())
            if time.monotonic() - last_persist >= PERSIST_SNAPSHOTS_EVERY_S:
                await repo.insert_snapshots(self.ctx.pool, datetime.now(tz=UTC), tick.symbols)
                last_persist = time.monotonic()

    async def run(self) -> None:
        self._publish_status()
        if not await self._initial_universe():
            return
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._consume())
            tg.create_task(self._backfill_loop())
            tg.create_task(self._publish_loop())
            tg.create_task(self._universe_loop())
