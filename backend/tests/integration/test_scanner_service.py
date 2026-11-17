"""ScannerService ponta a ponta: WS falso + REST falso + Postgres/Redis reais."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import pytest
from aiohttp import web

from quantum_one.bus.redis_client import create_redis
from quantum_one.core.config import Settings
from quantum_one.core.health import HealthState
from quantum_one.db.instruments import upsert_instruments
from quantum_one.db.pool import create_pool
from quantum_one.exchange.binance.client import build_exchange
from quantum_one.exchange.binance.filters import parse_instrument
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.rate_limit import BAN_KEY, MemoryBanStore, WeightBudget
from quantum_one.services.runtime import ServiceContext
from quantum_one.services.scanner_service import ScannerService
from tests.fakes.binance_payloads import BTCUSDT
from tests.fakes.fake_binance import FakeBinance, point_exchange_to, start
from tests.fakes.fake_ws import FakeStreamServer, book_frame, depth_frame, kline_frame, start_ws

pytestmark = pytest.mark.integration
M = 60_000


async def _wait(cond: Callable[[], Any], max_s: float = 10) -> None:
    for _ in range(int(max_s / 0.05)):
        if await cond() if asyncio.iscoroutinefunction(cond) else cond():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condição não atingida")


async def test_scanner_end_to_end(settings_for: Callable[[str], Settings]) -> None:
    now = int(time.time() * 1000)
    minute = now - now % M
    fake_rest = FakeBinance(hmac_secret="x" * 20)
    rest_server = await start(fake_rest)

    async def script(ws: web.WebSocketResponse, i: int) -> None:
        if i == 0:
            # vela fechada do minuto anterior (já coberta pelo aquecimento) e uma 3 min à frente
            # → lacuna; depois livro e silêncio para forçar 'stale' e reconexão
            await ws.send_str(kline_frame("BTCUSDT", minute - M, "60001.00", True))
            await ws.send_str(book_frame("BTCUSDT", "59999.00", "60001.00", "2"))
            await ws.send_str(
                depth_frame(
                    "BTCUSDT", [["59999", "2"], ["59000", "5"]], [["60001", "2"], ["61000", "5"]]
                )
            )
            await asyncio.sleep(10)
        else:
            for _ in range(200):
                await ws.send_str(book_frame("BTCUSDT", "59999.00", "60001.00"))
                await asyncio.sleep(0.05)

    fake_ws = FakeStreamServer(script)
    ws_server, ws_base = await start_ws(fake_ws)

    settings = settings_for("q1_marketdata").model_copy(
        update={
            "binance_ws_url": ws_base,
            "scanner_stale_after_s": 3.0,
            "scanner_snapshot_interval_s": 1.0,
            "scanner_warmup_candles": 120,
        }
    )
    ctx = ServiceContext(
        settings,
        await create_pool(settings),
        create_redis(settings),
        HealthState("marketdata", "test"),
        asyncio.Event(),
    )
    exchange = build_exchange(settings, authenticated=False)
    point_exchange_to(exchange, rest_server)
    gateway = BinanceReadGateway(exchange, WeightBudget(MemoryBanStore()))
    await ctx.redis.delete(BAN_KEY, "md:candles", "md:scanner", "md:health")
    await upsert_instruments(ctx.pool, [parse_instrument(BTCUSDT)])

    svc = ScannerService(ctx, gateway)
    task = asyncio.create_task(svc.run())
    try:
        # aquecimento: ~120 velas REST + vela do stream
        await _wait(
            lambda: "BTCUSDT" in svc.state.universe and len(svc.state.series("BTCUSDT")) >= 120
        )
        assert svc.state.series("BTCUSDT").internal_gaps() == 0
        assert svc.state.universe == ["BTCUSDT"]

        # snapshots publicados com métricas do livro
        async def has_tick() -> bool:
            return bool(await ctx.redis.xlen("md:scanner"))

        await _wait(has_tick)
        _, fields = (await ctx.redis.xrevrange("md:scanner", count=1))[0]
        env = json.loads(fields["data"])
        assert env["type"] == "scanner.tick" and env["source"] == "marketdata"
        sym = env["payload"]["symbols"][0]
        assert sym["symbol"] == "BTCUSDT" and sym["spread_bps"] is not None

        # silêncio > 3 s → stale + reconexão
        await _wait(lambda: len(fake_ws.connections) >= 2, max_s=10)
        assert ctx.state.extra["scanner"]["reconnects"] >= 1

        # velas persistidas e publicadas (REST = backfill)
        count = await ctx.pool.fetchval(
            "SELECT count(*) FROM q1.candles WHERE symbol = 'BTCUSDT' AND open_time >= "
            "to_timestamp($1 / 1000.0)",
            minute - 200 * M,
        )
        assert count >= 120
        sources = {
            r["source"]
            for r in await ctx.pool.fetch(
                "SELECT DISTINCT source FROM q1.candles WHERE symbol = 'BTCUSDT'"
            )
        }
        assert "rest" in sources
        entries = await ctx.redis.xrange("md:candles")
        flags = [json.loads(f["data"])["payload"]["backfill"] for _, f in entries]
        assert True in flags and False in flags  # stream e REST convivem
        times = [json.loads(f["data"])["payload"]["open_time"] for _, f in entries]
        assert len(times) == len(set(times))  # sem publicação duplicada da mesma vela
        assert await ctx.redis.xlen("md:health") >= 1
    finally:
        ctx.stop.set()
        started = time.monotonic()
        await asyncio.wait_for(task, timeout=10)
        # desligamento limitado: silêncio (3 s) ou fechamento do WS (2 s), nunca indefinido
        assert time.monotonic() - started < 6
        await gateway.close()
        await ws_server.close()
        await rest_server.close()
        await ctx.redis.aclose()
        await ctx.pool.close()


async def test_universe_unavailable_reports_status(settings_for: Callable[[str], Settings]) -> None:
    settings = settings_for("q1_marketdata")
    ctx = ServiceContext(
        settings,
        await create_pool(settings),
        create_redis(settings),
        HealthState("marketdata", "test"),
        asyncio.Event(),
    )

    class BrokenRest:
        async def klines(self, *a: Any, **k: Any) -> list[Any]:
            return []

        async def quote_volumes_24h(self) -> dict[str, float]:
            raise ConnectionError("binance fora")

    svc = ScannerService(ctx, BrokenRest())
    task = asyncio.create_task(svc.run())
    try:
        await _wait(lambda: "error" in ctx.state.extra.get("scanner", {}))
        assert ctx.state.extra["scanner"]["connected"] is False
    finally:
        ctx.stop.set()
        await asyncio.wait_for(task, timeout=5)
        await ctx.redis.aclose()
        await ctx.pool.close()


class ScriptedSource:
    """Fonte de eventos controlada pelo teste (sem rede)."""

    def __init__(self, events: list[Any]) -> None:
        self.events_list, self.connected, self.reconnects, self.unknown_messages = (
            events,
            False,
            0,
            0,
        )
        self.reconnect_requests = 0

    def request_reconnect(self) -> None:
        self.reconnect_requests += 1

    async def events(self, stop: asyncio.Event):  # type: ignore[no-untyped-def]
        for ev in self.events_list:
            yield ev
        await stop.wait()


class FlakyRest:
    def __init__(self, base: Any) -> None:
        self.base, self.failures_left, self.volumes = base, 1, {"BTCUSDT": 9e8}

    async def klines(self, *a: Any) -> list[Any]:
        if self.failures_left:
            self.failures_left -= 1
            raise ConnectionError("rede instável")
        return await self.base.klines(*a)

    async def quote_volumes_24h(self) -> dict[str, float]:
        return self.volumes


async def test_stream_gap_backfill_retry_and_universe_change(
    settings_for: Callable[[str], Settings], connect: Any
) -> None:
    from quantum_one.marketdata.messages import parse_frame
    from quantum_one.marketdata.models import Connected
    from tests.fakes.fake_ws import kline_frame

    now = int(time.time() * 1000)
    minute = now - now % M
    fake_rest = FakeBinance(hmac_secret="x" * 20)
    rest_server = await start(fake_rest)
    settings = settings_for("q1_marketdata").model_copy(update={"scanner_warmup_candles": 60})
    ctx = ServiceContext(
        settings,
        await create_pool(settings),
        create_redis(settings),
        HealthState("marketdata", "test"),
        asyncio.Event(),
    )
    exchange = build_exchange(settings, authenticated=False)
    point_exchange_to(exchange, rest_server)
    rest = FlakyRest(BinanceReadGateway(exchange, WeightBudget(MemoryBanStore())))
    await upsert_instruments(ctx.pool, [parse_instrument(BTCUSDT)])

    # vela de 5 min atrás e depois a do minuto anterior → lacuna de 3 velas pelo stream
    source = ScriptedSource(
        [
            parse_frame(kline_frame("BTCUSDT", minute - 5 * M, "60000.00", True)),
            Connected("ws://fake"),
            parse_frame(kline_frame("BTCUSDT", minute - M, "60001.00", True)),
        ]
    )
    svc = ScannerService(ctx, rest, stream_factory=lambda url: source)
    task = asyncio.create_task(svc.run())
    try:

        def gap_filled() -> bool:
            if "BTCUSDT" not in svc.state.universe:
                return False
            s = svc.state.series("BTCUSDT")
            return len(s) >= 5 and s.internal_gaps() == 0

        await _wait(gap_filled, max_s=15)  # a 1ª tentativa falha; o retry ocorre em ~5 s
        times = [c.open_time_ms for c in svc.state.series("BTCUSDT").candles()]
        assert times[:5] == [minute - k * M for k in (5, 4, 3, 2, 1)]
        assert rest.failures_left == 0  # a 1ª tentativa falhou e foi refeita

        # universo muda → reconexão pedida ao stream
        await upsert_instruments(
            ctx.pool, [parse_instrument({**BTCUSDT, "symbol": "ETHUSDT", "baseAsset": "ETH"})]
        )
        rest.volumes = {"BTCUSDT": 9e8, "ETHUSDT": 8e8}
        assert await svc.refresh_universe() is True
        assert svc.state.universe == ["BTCUSDT", "ETHUSDT"]
        assert await svc.refresh_universe() is False
    finally:
        owner = await connect("q1_migrator")  # isolamento: remove o instrumento extra
        await owner.execute("DELETE FROM q1.instruments WHERE symbol = 'ETHUSDT'")
        await owner.close()
        ctx.stop.set()
        await asyncio.wait_for(task, timeout=10)
        await rest.base.close()
        await rest_server.close()
        await ctx.redis.aclose()
        await ctx.pool.close()
