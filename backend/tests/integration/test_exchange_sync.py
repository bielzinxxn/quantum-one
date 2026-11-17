"""Sincronização marketdata/trader com Postgres+Redis reais e o servidor Binance falso."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import asyncpg
import pytest
from aiohttp.test_utils import TestServer
from pydantic import SecretStr

from quantum_one.bus.redis_client import create_redis
from quantum_one.core.config import Settings
from quantum_one.core.health import HealthState
from quantum_one.db.pool import create_pool
from quantum_one.exchange.binance.client import build_exchange
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.rate_limit import BAN_KEY, RedisBanStore, WeightBudget
from quantum_one.services import account_sync, instruments_sync
from quantum_one.services.exchange_status import ExchangeStatus
from quantum_one.services.runtime import ServiceContext
from tests.fakes.fake_binance import FakeBinance, point_exchange_to, start

pytestmark = pytest.mark.integration
SECRET = "hmac-secret-for-tests-0123456789abcdef"


async def _ctx(settings: Settings) -> ServiceContext:
    return ServiceContext(
        settings=settings,
        pool=await create_pool(settings),
        redis=create_redis(settings),
        state=HealthState(settings.service_name, "test"),
        stop=asyncio.Event(),
    )


async def _close(ctx: ServiceContext) -> None:
    await ctx.redis.aclose()
    await ctx.pool.close()


@pytest.fixture
async def fake() -> AsyncIterator[tuple[FakeBinance, TestServer]]:
    f = FakeBinance(hmac_secret=SECRET)
    server = await start(f)
    yield f, server
    await server.close()


def _gateway(
    settings: Settings, server: TestServer, ctx: ServiceContext, auth: bool
) -> BinanceReadGateway:
    ex = build_exchange(settings, authenticated=auth)
    point_exchange_to(ex, server)
    return BinanceReadGateway(ex, WeightBudget(RedisBanStore(ctx.redis)))


async def test_instruments_cycle_upserts(
    settings_for: Callable[[str], Settings], fake: Any, connect: Any
) -> None:
    _, server = fake
    ctx = await _ctx(settings_for("q1_marketdata"))
    gw = _gateway(ctx.settings, server, ctx, auth=False)
    status = ExchangeStatus()
    try:
        await ctx.redis.delete(BAN_KEY)
        await instruments_sync.run_cycle(ctx, gw, status)
        await instruments_sync.run_cycle(ctx, gw, status)  # idempotente
        assert status.state == "ok"
        assert status.details == {"instruments": 2, "tradable_usdt": 1}
        assert status.clock_offset_ms is not None
        conn = await connect("q1_engine")  # outros serviços leem
        try:
            row = await conn.fetchrow("SELECT * FROM instruments WHERE symbol = 'BTCUSDT'")
            assert str(row["tick_size"].normalize()) == "0.01"
            assert row["order_types"][0] == "LIMIT"
        finally:
            await conn.close()
    finally:
        await gw.close()
        await _close(ctx)


async def test_clock_drift_blocks_instrument_sync(
    settings_for: Callable[[str], Settings], fake: Any
) -> None:
    f, server = fake
    f.server_time_offset_ms = 10_000
    ctx = await _ctx(settings_for("q1_marketdata"))
    gw = _gateway(ctx.settings, server, ctx, auth=False)
    status = ExchangeStatus()
    try:
        await instruments_sync.run_cycle(ctx, gw, status)
        assert status.state == "blocked"
        assert "relógio" in status.reasons[0]
    finally:
        await gw.close()
        await _close(ctx)


async def test_account_sync_writes_snapshot(
    settings_for: Callable[[str], Settings], fake: Any, connect: Any
) -> None:
    _, server = fake
    settings = settings_for("q1_trader").model_copy(
        update={
            "binance_api_key": SecretStr("test-api-key"),
            "binance_api_secret": SecretStr(SECRET),
        }
    )
    ctx = await _ctx(settings)
    gw = _gateway(settings, server, ctx, auth=True)
    status = ExchangeStatus()
    try:
        await account_sync.check_key(ctx, gw)
        assert await account_sync.sync_account(ctx, gw, status)
        assert status.state == "ok" and status.details["open_orders"] == 1
        conn = await connect("q1_accounting")
        try:
            snap = await conn.fetchrow("SELECT * FROM account_snapshots ORDER BY id DESC LIMIT 1")
            assert snap["open_orders"] == 1 and snap["account_type"] == "SPOT"
            rows = await conn.fetch(
                "SELECT asset, free::text, locked::text FROM balance_snapshots "
                "WHERE snapshot_id = $1 ORDER BY asset",
                snap["id"],
            )
            assert [r["asset"] for r in rows] == ["BTC", "USDT"]
            assert rows[1]["free"].startswith("1500.12345678")
        finally:
            await conn.close()
    finally:
        await gw.close()
        await _close(ctx)


async def test_key_with_withdrawals_is_rejected(
    settings_for: Callable[[str], Settings], fake: Any
) -> None:
    f, server = fake
    f.key_permissions["enableWithdrawals"] = True
    settings = settings_for("q1_trader").model_copy(
        update={
            "binance_api_key": SecretStr("test-api-key"),
            "binance_api_secret": SecretStr(SECRET),
        }
    )
    ctx = await _ctx(settings)
    gw = _gateway(settings, server, ctx, auth=True)
    try:
        with pytest.raises(account_sync.KeyPolicyViolation, match="saque"):
            await account_sync.check_key(ctx, gw)
    finally:
        await gw.close()
        await _close(ctx)


async def test_trader_without_credentials_stays_blocked(
    settings_for: Callable[[str], Settings],
) -> None:
    ctx = await _ctx(settings_for("q1_trader"))
    try:
        task = asyncio.create_task(account_sync.account_work(ctx))
        await asyncio.sleep(0.2)
        assert ctx.state.extra["trading_state"] == "BLOCKED"
        assert ctx.state.extra["exchange"]["state"] == "credentials_missing"
        ctx.stop.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        await _close(ctx)


async def test_table_grants(connect: Any) -> None:
    md = await connect("q1_marketdata")
    trader = await connect("q1_trader")
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await md.execute(
                "INSERT INTO account_snapshots (taken_at, source, account_type, "
                "can_trade, maker_commission, taker_commission, open_orders) "
                "VALUES (now(), 'exchange', 'SPOT', true, 0, 0, 0)"
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await trader.execute("UPDATE instruments SET status = 'HALT'")
    finally:
        await md.close()
        await trader.close()
