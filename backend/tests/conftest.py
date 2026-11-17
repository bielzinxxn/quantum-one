from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

VALID_ENV = {
    "SERVICE_NAME": "test",
    "POSTGRES_USER": "q1_test",
    "POSTGRES_PASSWORD": "pg-secret-value-0123456789",
    "REDIS_PASSWORD": "redis-secret-value-0123456789",
}


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key in (
        "TRADING_MODE",
        "LIVE_TRADING_ENABLED",
        "QONE_ENV",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "LOG_LEVEL",
        "BINANCE_KEY_POLICY",
        "BINANCE_TESTNET",
        "BINANCE_RECV_WINDOW_MS",
        "CLOCK_MAX_OFFSET_MS",
        "ACCOUNT_POLL_S",
        "BINANCE_WS_URL",
        "SCANNER_EXTRA_SYMBOLS",
        "SCANNER_STALE_AFTER_S",
        "SCANNER_UNIVERSE_SIZE",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(VALID_ENV)
