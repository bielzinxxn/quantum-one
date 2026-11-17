"""Gateway de leitura da Binance Spot.

Cada chamada: reserva peso no orçamento → executa endpoint implícito do CCXT →
observa cabeçalho de peso → converte JSON bruto para Decimal. Erros de rate limit
registram backoff compartilhado antes de propagar.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from quantum_one.exchange.binance import filters, parsers
from quantum_one.exchange.errors import ErrorKind, classify
from quantum_one.exchange.models import (
    AccountSnapshot,
    AccountTrade,
    Instrument,
    KeyPermissions,
    OpenOrder,
    RateLimit,
    SymbolCommission,
)
from quantum_one.exchange.rate_limit import WeightBudget
from quantum_one.marketdata.models import Candle

# pesos da doc oficial (docs/referencias/binance-spot-api.md)
W_TIME, W_EXCHANGE_INFO, W_ACCOUNT, W_COMMISSION = 1, 20, 20, 20
W_OPEN_ORDERS_ONE, W_OPEN_ORDERS_ALL, W_MY_TRADES = 6, 80, 20
W_API_RESTRICTIONS = 1  # não documentado na doc spot; conservador
W_KLINES, W_TICKER_24H_ALL = 2, 80


class BinanceReadGateway:
    def __init__(self, exchange: Any, budget: WeightBudget) -> None:
        self._ex = exchange
        self._budget = budget

    async def _call(self, method: str, cost: int, params: dict[str, Any] | None = None) -> Any:
        fn: Callable[[dict[str, Any]], Awaitable[Any]] = getattr(self._ex, method)
        await self._budget.acquire(cost)
        try:
            result = await fn(params or {})
        except Exception as exc:
            kind = classify(exc).kind
            if kind in (ErrorKind.RATE_LIMITED, ErrorKind.IP_BANNED):
                await self._budget.on_rate_limited(
                    self._ex.last_response_headers, banned=kind is ErrorKind.IP_BANNED
                )
            raise
        self._budget.observe(self._ex.last_response_headers)
        return result

    @property
    def weight_used(self) -> int:
        return self._budget.used

    async def server_time_ms(self) -> int:
        raw = await self._call("public_get_time", W_TIME)
        return int(raw["serverTime"])

    async def exchange_info(self) -> tuple[list[Instrument], list[RateLimit]]:
        raw = await self._call("public_get_exchangeinfo", W_EXCHANGE_INFO)
        limits = parsers.parse_rate_limits(raw.get("rateLimits", []))
        weight_limit = parsers.weight_limit_per_minute(limits)
        if weight_limit:
            self._budget.set_limit(weight_limit)
        instruments = [filters.parse_instrument(s) for s in raw.get("symbols", [])]
        return instruments, limits

    async def key_permissions(self) -> KeyPermissions:
        raw = await self._call("sapi_get_account_apirestrictions", W_API_RESTRICTIONS)
        return parsers.parse_key_permissions(raw)

    async def account(self) -> AccountSnapshot:
        raw = await self._call("private_get_account", W_ACCOUNT, {"omitZeroBalances": "true"})
        return parsers.parse_account(raw)

    async def open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        params = {"symbol": symbol} if symbol else {}
        cost = W_OPEN_ORDERS_ONE if symbol else W_OPEN_ORDERS_ALL
        raw = await self._call("private_get_openorders", cost, params)
        return [parsers.parse_open_order(o) for o in raw]

    async def my_trades(
        self, symbol: str, from_id: int | None = None, limit: int = 500
    ) -> list[AccountTrade]:
        params: dict[str, Any] = {"symbol": symbol, "limit": min(max(limit, 1), 1000)}
        if from_id is not None:
            params["fromId"] = from_id
        raw = await self._call("private_get_mytrades", W_MY_TRADES, params)
        return [parsers.parse_trade(t) for t in raw]

    async def commission(self, symbol: str) -> SymbolCommission:
        raw = await self._call("private_get_account_commission", W_COMMISSION, {"symbol": symbol})
        return parsers.parse_commission(raw)

    async def klines(
        self, symbol: str, interval: str, start_ms: int, end_ms: int | None, limit: int
    ) -> list[Candle]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_ms,
            "limit": min(max(limit, 1), 1000),
        }
        if end_ms is not None:
            params["endTime"] = end_ms
        raw = await self._call("public_get_klines", W_KLINES, params)
        return [parsers.parse_rest_kline(symbol, row) for row in raw]

    async def quote_volumes_24h(self) -> dict[str, float]:
        raw = await self._call("public_get_ticker_24hr", W_TICKER_24H_ALL)
        return parsers.parse_quote_volumes(raw)

    async def close(self) -> None:
        await self._ex.close()
