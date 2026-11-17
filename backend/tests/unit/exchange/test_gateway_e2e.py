"""Gateway + CCXT REAL contra o servidor Binance falso: assinatura, pesos, erros."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal as D
from typing import Any

import pytest
from aiohttp.test_utils import TestServer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from quantum_one.core.config import load_settings
from quantum_one.exchange.binance.client import build_exchange
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.errors import ErrorKind, classify
from quantum_one.exchange.rate_limit import MemoryBanStore, RateLimitedError, WeightBudget
from tests.fakes.fake_binance import FakeBinance, point_exchange_to, start

HMAC_SECRET = "hmac-secret-for-tests-0123456789abcdef"


@dataclass
class Env:
    fake: FakeBinance
    server: TestServer
    gateway: BinanceReadGateway
    budget: WeightBudget
    store: MemoryBanStore


def _ed25519_pem() -> tuple[str, Any]:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


async def _make(monkeypatch: pytest.MonkeyPatch, fake: FakeBinance, secret: str) -> Env:
    monkeypatch.setenv("BINANCE_API_KEY", fake.api_key)
    monkeypatch.setenv("BINANCE_API_SECRET", secret)
    server = await start(fake)
    exchange = build_exchange(load_settings(), authenticated=True)
    point_exchange_to(exchange, server)
    store = MemoryBanStore()
    budget = WeightBudget(store)
    return Env(fake, server, BinanceReadGateway(exchange, budget), budget, store)


@pytest.fixture
async def hmac_env(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Env]:
    env = await _make(monkeypatch, FakeBinance(hmac_secret=HMAC_SECRET), HMAC_SECRET)
    yield env
    await env.gateway.close()
    await env.server.close()


async def test_full_read_flow_hmac(hmac_env: Env) -> None:
    gw = hmac_env.gateway
    assert await gw.server_time_ms() > 0
    instruments, _limits = await gw.exchange_info()
    assert {i.symbol for i in instruments} == {"BTCUSDT", "ETHBTC"}
    assert hmac_env.budget.ceiling == int(6000 * 0.8)
    perms = await gw.key_permissions()
    assert perms.enable_reading and not perms.enable_withdrawals
    account = await gw.account()
    assert {b.asset for b in account.balances} == {"BTC", "USDT"}
    assert len(await gw.open_orders()) == 1
    trades = await gw.my_trades("BTCUSDT", from_id=28000, limit=5000)
    assert trades[0].price == D("60000.1")
    assert (await gw.commission("BTCUSDT")).bnb_discount_multiplier == D("0.75")
    # cabeçalho X-MBX-USED-WEIGHT-1M foi observado
    assert hmac_env.budget.used >= hmac_env.fake.used_weight


async def test_signed_requests_carry_recvwindow_5000_and_params(hmac_env: Env) -> None:
    await hmac_env.gateway.account()
    await hmac_env.gateway.my_trades("BTCUSDT", from_id=7, limit=5000)
    queries = {r["path"]: r["query"] for r in hmac_env.fake.requests}
    assert "recvWindow=5000" in queries["/api/v3/account"]
    assert "omitZeroBalances=true" in queries["/api/v3/account"]
    assert "fromId=7" in queries["/api/v3/myTrades"]
    assert "limit=1000" in queries["/api/v3/myTrades"]  # limitado ao máximo documentado


async def test_ed25519_signature_accepted(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pem, public = _ed25519_pem()
    escaped = pem.strip().replace("\n", "\\n")  # como fica numa linha do .env
    env = await _make(monkeypatch, FakeBinance(ed25519_public=public), escaped)
    try:
        assert (await env.gateway.key_permissions()).enable_reading
        assert len((await env.gateway.account()).balances) == 2
    finally:
        await env.gateway.close()
        await env.server.close()


async def test_wrong_secret_is_rejected(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    env = await _make(
        monkeypatch, FakeBinance(hmac_secret=HMAC_SECRET), "outro-secret-qualquer-123"
    )
    try:
        with pytest.raises(Exception) as exc:  # noqa: PT011 — classificado abaixo
            await env.gateway.account()
        assert classify(exc.value).code == -1022
    finally:
        await env.gateway.close()
        await env.server.close()


async def test_429_sets_shared_backoff_from_retry_after(hmac_env: Env) -> None:
    hmac_env.fake.fail(
        "/api/v3/account", 429, -1003, "Too much request weight used", {"Retry-After": "45"}
    )
    with pytest.raises(Exception) as exc:  # noqa: PT011
        await hmac_env.gateway.account()
    assert classify(exc.value).kind is ErrorKind.RATE_LIMITED
    assert await hmac_env.store.get_banned_until() > 0
    with pytest.raises(RateLimitedError):
        await hmac_env.gateway.server_time_ms()  # nem chega a sair: backoff compartilhado


async def test_418_ip_ban(hmac_env: Env) -> None:
    hmac_env.fake.fail("/api/v3/exchangeInfo", 418, -1003, "IP banned", {"Retry-After": "600"})
    with pytest.raises(Exception) as exc:  # noqa: PT011
        await hmac_env.gateway.exchange_info()
    assert classify(exc.value).kind is ErrorKind.IP_BANNED
    with pytest.raises(RateLimitedError) as blocked:
        await hmac_env.gateway.server_time_ms()
    assert blocked.value.wait_s > 590


async def test_timestamp_error_classified_as_clock(hmac_env: Env) -> None:
    hmac_env.fake.fail(
        "/api/v3/account", 400, -1021, "Timestamp for this request is outside of the recvWindow."
    )
    with pytest.raises(Exception) as exc:  # noqa: PT011
        await hmac_env.gateway.account()
    assert classify(exc.value).kind is ErrorKind.CLOCK


async def test_invalid_key_classified_as_auth(hmac_env: Env) -> None:
    hmac_env.fake.fail(
        "/sapi/v1/account/apiRestrictions",
        401,
        -2015,
        "Invalid API-key, IP, or permissions for action.",
    )
    with pytest.raises(Exception) as exc:  # noqa: PT011
        await hmac_env.gateway.key_permissions()
    assert classify(exc.value).kind is ErrorKind.AUTH


async def test_klines_and_24h_volumes(hmac_env: Env) -> None:
    hmac_env.fake.now_ms = 1_700_000_040_000 + 10 * 60_000 + 5_000
    rows = await hmac_env.gateway.klines("BTCUSDT", "1m", 1_700_000_040_000, None, 1000)
    assert len(rows) == 11  # 10 fechadas + a em andamento (o filtro é do backfill)
    assert rows[0].open_time_ms == 1_700_000_040_000
    assert rows[0].quote_volume == D("90000.0") and rows[0].trades == 42
    q = next(r["query"] for r in hmac_env.fake.requests if r["path"] == "/api/v3/klines")
    assert "interval=1m" in q and "startTime=1700000040000" in q
    volumes = await hmac_env.gateway.quote_volumes_24h()
    assert volumes["BTCUSDT"] == 9e8
