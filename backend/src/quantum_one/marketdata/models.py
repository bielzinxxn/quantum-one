"""Modelos internos do scanner. Velas em Decimal; livro em float (só métricas)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ONE_MINUTE_MS = 60_000


@dataclass(frozen=True)
class Candle:
    symbol: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int
    timeframe: str = "1m"


@dataclass(frozen=True)
class KlineUpdate:
    candle: Candle
    closed: bool


@dataclass(frozen=True)
class BookTop:
    symbol: str
    bid: float
    bid_qty: float
    ask: float
    ask_qty: float


@dataclass(frozen=True)
class Depth:
    symbol: str
    bids: tuple[tuple[float, float], ...]  # (preço, qtd), melhor primeiro
    asks: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class ServerShutdown:
    shutdown_at_ms: int | None


@dataclass(frozen=True)
class Connected:
    url: str


@dataclass(frozen=True)
class Disconnected:
    reason: str


StreamEvent = KlineUpdate | BookTop | Depth | ServerShutdown | Connected | Disconnected
