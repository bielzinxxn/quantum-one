"""Interface de leitura da exchange. Backtest/paper/live terão implementações próprias (ADR-004)."""

from __future__ import annotations

from typing import Protocol

from quantum_one.exchange.models import (
    AccountSnapshot,
    AccountTrade,
    Instrument,
    KeyPermissions,
    OpenOrder,
    RateLimit,
    SymbolCommission,
)


class ReadOnlyGateway(Protocol):
    async def server_time_ms(self) -> int: ...
    async def exchange_info(self) -> tuple[list[Instrument], list[RateLimit]]: ...
    async def key_permissions(self) -> KeyPermissions: ...
    async def account(self) -> AccountSnapshot: ...
    async def open_orders(self, symbol: str | None = None) -> list[OpenOrder]: ...
    async def my_trades(
        self, symbol: str, from_id: int | None = None, limit: int = 500
    ) -> list[AccountTrade]: ...
    async def commission(self, symbol: str) -> SymbolCommission: ...
    async def close(self) -> None: ...
