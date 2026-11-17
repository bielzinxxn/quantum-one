"""Payloads dos streams de mercado: md:candles, md:scanner, md:health."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

STREAM_CANDLES = "md:candles"
STREAM_SCANNER = "md:scanner"
STREAM_HEALTH = "md:health"


class CandleClosed(BaseModel):
    """Vela 1m fechada. ORDEM NÃO GARANTIDA entre stream e backfill (uma vela do stream pode
    chegar antes das velas antigas do aquecimento/lacuna). Consumidores devem ordenar por
    `open_time` e deduplicar por (symbol, timeframe, open_time)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int
    backfill: bool  # True = veio do REST (lacuna/aquecimento), não do stream


class SymbolSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    stale: bool
    data_age_s: float | None
    book_age_s: float | None
    last_close: Decimal | None
    bid: float | None
    ask: float | None
    spread_bps: float | None
    depth_bid_quote_0_5pct: float | None
    depth_ask_quote_0_5pct: float | None
    depth_bid_quote_1pct: float | None
    depth_ask_quote_1pct: float | None
    depth_truncated: bool
    slippage_buy_bps: float | None  # comprar `probe` em quote, contra o mid
    slippage_sell_bps: float | None
    ret_5m: float | None
    ret_15m: float | None
    ret_60m: float | None
    return_z_1m: float | None  # retorno do último minuto em desvios-padrão
    rel_volume_1m: float | None  # volume do último minuto / mediana recente
    realized_vol_1h: float | None  # anualizada
    realized_vol_12h: float | None
    candles: int
    flags: list[str]


class ScannerTick(BaseModel):
    model_config = ConfigDict(frozen=True)

    at: datetime
    connected: bool
    universe: list[str]
    symbols: list[SymbolSnapshot]
