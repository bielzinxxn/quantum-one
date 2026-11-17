"""`make check-binance` contra o servidor falso: códigos de saída, sem segredos na saída."""

from __future__ import annotations

import pytest

from quantum_one.core.config import load_settings
from quantum_one.exchange.binance.client import build_exchange
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.rate_limit import MemoryBanStore, WeightBudget
from quantum_one.services.check_binance import run_checks
from tests.fakes.fake_binance import FakeBinance, point_exchange_to, start

SECRET = "hmac-secret-for-tests-0123456789abcdef"


async def _run(fake: FakeBinance, authenticated: bool = True) -> tuple[int, list[str]]:
    settings = load_settings()
    server = await start(fake)
    exchange = build_exchange(settings, authenticated=authenticated)
    point_exchange_to(exchange, server)
    lines: list[str] = []
    try:
        code = await run_checks(
            settings, lines.append, BinanceReadGateway(exchange, WeightBudget(MemoryBanStore()))
        )
    finally:
        await server.close()
    return code, lines


@pytest.fixture
def creds(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "test-api-key")
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET)


async def test_all_ok(creds: None) -> None:
    code, lines = await _run(FakeBinance(hmac_secret=SECRET))
    text = "\n".join(lines)
    assert code == 0, text
    assert "política da chave atendida" in text
    assert "USDT" in text and "ordens abertas: 1" in text
    assert "tipo de chave: hmac" in text
    assert "HMAC depreciadas" in text
    assert SECRET not in text and "test-api-key" not in text


async def test_withdrawal_enabled_key_fails_with_code_2(creds: None) -> None:
    fake = FakeBinance(hmac_secret=SECRET)
    fake.key_permissions["enableWithdrawals"] = True
    code, lines = await _run(fake)
    assert code == 2
    assert any("saque habilitado" in line for line in lines)


async def test_trading_key_rejected_under_read_only(creds: None) -> None:
    fake = FakeBinance(hmac_secret=SECRET)
    fake.key_permissions["enableSpotAndMarginTrading"] = True
    code, _ = await _run(fake)
    assert code == 2


async def test_ip_restriction_required_in_prod(
    creds: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QONE_ENV", "prod")
    fake = FakeBinance(hmac_secret=SECRET)
    fake.key_permissions["ipRestrict"] = False
    code, lines = await _run(fake)
    assert code == 2
    assert any("restrição de IP" in line for line in lines)


async def test_clock_drift_fails_with_code_4(creds: None) -> None:
    code, lines = await _run(FakeBinance(hmac_secret=SECRET, server_time_offset_ms=5000))
    assert code == 4
    assert any("relógio" in line and "FALHA" in line for line in lines)


async def test_without_credentials_runs_public_checks_only(valid_env: dict[str, str]) -> None:
    code, lines = await _run(FakeBinance(hmac_secret=SECRET), authenticated=False)
    assert code == 3
    assert any("exchangeInfo" in line for line in lines)


async def test_api_error_exit_1(creds: None) -> None:
    fake = FakeBinance(hmac_secret=SECRET)
    fake.fail("/api/v3/account", 401, -2015, "Invalid API-key, IP, or permissions for action.")
    code, lines = await _run(fake)
    assert code == 1
    assert any("auth" in line for line in lines)
