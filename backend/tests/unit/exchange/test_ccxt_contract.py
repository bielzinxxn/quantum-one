"""Contrato com o CCXT instalado: se uma atualização remover rotas ou mudar URLs, falha aqui."""

from __future__ import annotations

import ccxt
import ccxt.pro as ccxtpro
import pytest

from quantum_one.core.config import load_settings
from quantum_one.exchange.binance.client import build_exchange, key_type

REQUIRED_IMPLICIT = (
    "public_get_time",
    "public_get_exchangeinfo",
    "private_get_account",
    "private_get_account_commission",
    "private_get_openorders",
    "private_get_mytrades",
    "sapi_get_account_apirestrictions",
)


def test_ccxt_version_pinned_major() -> None:
    assert ccxt.__version__.startswith("4.")


async def test_implicit_methods_and_spot_urls(valid_env: dict[str, str]) -> None:
    ex = build_exchange(load_settings(), authenticated=False)
    try:
        for name in REQUIRED_IMPLICIT:
            assert callable(getattr(ex, name)), name
        assert ex.urls["api"]["public"] == "https://api.binance.com/api/v3"
        assert ex.urls["api"]["sapi"] == "https://api.binance.com/sapi/v1"
        assert ex.urls["api"]["ws"]["ws-api"]["spot"].startswith("wss://ws-api.binance.com")
        assert ex.options["recvWindow"] == 5000
        assert ex.options["adjustForTimeDifference"] is False
        assert ex.has["watchBalance"] and ex.has["watchOrderBook"]
    finally:
        await ex.close()


async def test_testnet_switches_urls(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINANCE_TESTNET", "true")
    ex = build_exchange(load_settings(), authenticated=False)
    try:
        assert "testnet.binance.vision" in ex.urls["api"]["public"]
    finally:
        await ex.close()


def test_authenticated_requires_credentials(valid_env: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="credenciais"):
        build_exchange(load_settings(), authenticated=True)


def test_key_type_matches_ccxt_rule() -> None:
    assert key_type("abc123") == "hmac"
    assert (
        key_type("-----BEGIN PRIVATE KEY-----\n" + "A" * 64 + "\n-----END PRIVATE KEY-----")
        == "ed25519"
    )
    assert (
        key_type("-----BEGIN PRIVATE KEY-----\n" + "A" * 1600 + "\n-----END PRIVATE KEY-----")
        == "rsa"
    )
    assert issubclass(ccxtpro.binance, ccxt.async_support.binance)
