"""Construção do cliente CCXT Pro para Binance Spot com opções seguras (ADR-008)."""

from __future__ import annotations

from typing import Any

import ccxt.pro as ccxtpro

from quantum_one.core.config import Settings


def build_exchange(settings: Settings, *, authenticated: bool) -> Any:
    config: dict[str, Any] = {
        "enableRateLimit": True,  # limitador do CCXT + nosso orçamento por cabeçalho
        "timeout": 10_000,
        "options": {
            "defaultType": "spot",
            "fetchMarkets": ["spot"],  # nunca carregar futuros/margem por acidente
            "recvWindow": settings.binance_recv_window_ms,
            "adjustForTimeDifference": False,  # medimos o relógio nós mesmos
        },
    }
    if authenticated:
        if not settings.has_binance_credentials:
            raise ValueError("credenciais da Binance ausentes")
        assert settings.binance_api_key is not None
        assert settings.binance_api_secret is not None
        config["apiKey"] = settings.binance_api_key.get_secret_value()
        config["secret"] = settings.binance_api_secret.get_secret_value()
    exchange = ccxtpro.binance(config)
    if settings.binance_testnet:
        exchange.set_sandbox_mode(True)
    return exchange


def key_type(secret: str) -> str:
    """Mesma regra do CCXT 4.5.92 (binance.sign): PEM curto = Ed25519, longo = RSA."""
    if "PRIVATE KEY" in secret:
        return "rsa" if len(secret) > 120 else "ed25519"
    return "hmac"
