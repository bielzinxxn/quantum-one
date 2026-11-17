"""Loops account_work / instruments_work: caminhos de sucesso, bloqueio e erro."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

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
from quantum_one.services.runtime import ServiceContext
from tests.fakes.fake_binance import FakeBinance, point_exchange_to, start

pytestmark = pytest.mark.integration
SECRET = "hmac-secret-for-tests-0123456789abcdef"


@pytest.fixture
async def fake() -> AsyncIterator[tuple[FakeBinance, TestServer]]:
    f = FakeBinance(hmac_secret=SECRET)
    server = await start(f)
    yield f, server
    await server.close()


async def _run_until(
    work: Any, ctx: ServiceContext, done: Callable[[dict[str, Any]], bool], max_s: float = 5
) -> dict[str, Any]:
    await ctx.redis.delete(BAN_KEY)
    task = asyncio.create_task(work)
    try:
        for _ in range(int(max_s / 0.05)):
            status = ctx.state.extra.get("exchange", {})
            if done(status):
                return dict(status)
            await asyncio.sleep(0.05)
        raise AssertionError(f"estado esperado não atingido: {ctx.state.extra}")
    finally:
        ctx.stop.set()
        await asyncio.wait_for(task, timeout=5)
        await ctx.redis.delete(BAN_KEY)
        await ctx.redis.aclose()
        await ctx.pool.close()


async def _ctx(settings: Settings) -> ServiceContext:
    return ServiceContext(
        settings,
        await create_pool(settings),
        create_redis(settings),
        HealthState(settings.service_name, "test"),
        asyncio.Event(),
    )


def _factory(server: TestServer, auth: bool) -> Callable[[ServiceContext], BinanceReadGateway]:
    def make(ctx: ServiceContext) -> BinanceReadGateway:
        ex = build_exchange(ctx.settings, authenticated=auth)
        point_exchange_to(ex, server)
        return BinanceReadGateway(ex, WeightBudget(RedisBanStore(ctx.redis)))

    return make


def _trader(settings_for: Callable[[str], Settings]) -> Settings:
    return settings_for("q1_trader").model_copy(
        update={
            "binance_api_key": SecretStr("test-api-key"),
            "binance_api_secret": SecretStr(SECRET),
        }
    )


async def test_account_loop_ok(settings_for: Any, fake: Any) -> None:
    _, server = fake
    ctx = await _ctx(_trader(settings_for))
    status = await _run_until(
        account_sync.account_work(ctx, _factory(server, True)),
        ctx,
        lambda s: s.get("state") == "ok",
    )
    assert status["details"]["assets"] == 2
    assert status["weight_used_1m"] > 0
    assert ctx.state.extra["trading_state"] == "BLOCKED"  # leitura OK não libera trading


async def test_account_loop_blocks_on_withdrawal_key(settings_for: Any, fake: Any) -> None:
    f, server = fake
    f.key_permissions["enableWithdrawals"] = True
    ctx = await _ctx(_trader(settings_for))
    status = await _run_until(
        account_sync.account_work(ctx, _factory(server, True)),
        ctx,
        lambda s: s.get("state") == "blocked",
    )
    assert any("saque" in r for r in status["reasons"])
    assert not any(r["path"] == "/api/v3/account" for r in f.requests)  # nem leu a conta


async def test_account_loop_degrades_on_429_and_shares_backoff(
    settings_for: Any, fake: Any
) -> None:
    f, server = fake
    f.fail("/api/v3/account", 429, -1003, "Too much request weight used", {"Retry-After": "120"})
    ctx = await _ctx(_trader(settings_for))
    redis = create_redis(ctx.settings)
    try:
        status = await _run_until(
            account_sync.account_work(ctx, _factory(server, True)),
            ctx,
            lambda s: s.get("state") == "degraded",
        )
        assert status["last_error"].startswith("rate_limited")
        assert float(await redis.get(BAN_KEY) or 0) == 0  # limpo pelo helper ao final
    finally:
        await redis.aclose()


async def test_account_loop_blocks_on_auth_error(settings_for: Any, fake: Any) -> None:
    f, server = fake
    f.fail("/sapi/v1/account/apiRestrictions", 401, -2015, "Invalid API-key, IP, or permissions")
    ctx = await _ctx(_trader(settings_for))
    status = await _run_until(
        account_sync.account_work(ctx, _factory(server, True)),
        ctx,
        lambda s: s.get("state") == "blocked",
    )
    assert status["last_error"] == "auth:-2015"


async def test_instruments_loop_ok_then_reports_weight(settings_for: Any, fake: Any) -> None:
    _, server = fake
    ctx = await _ctx(settings_for("q1_marketdata"))
    status = await _run_until(
        instruments_sync.instruments_work(ctx, _factory(server, False)),
        ctx,
        lambda s: s.get("state") == "ok",
    )
    assert status["details"]["instruments"] == 2


async def test_instruments_loop_survives_exchange_outage(settings_for: Any, fake: Any) -> None:
    f, server = fake
    f.fail("/api/v3/exchangeInfo", 503, -1001, "Internal error; unable to process your request.")
    ctx = await _ctx(settings_for("q1_marketdata"))
    status = await _run_until(
        instruments_sync.instruments_work(ctx, _factory(server, False)),
        ctx,
        lambda s: s.get("state") == "degraded",
    )
    assert status["last_error"] is not None
