"""Repositório de velas e snapshots do scanner."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import asyncpg

from quantum_one.contracts.market import SymbolSnapshot
from quantum_one.exchange.models import Instrument
from quantum_one.marketdata.models import Candle

_UPSERT_CANDLE = """
INSERT INTO q1.candles (symbol, timeframe, open_time, open, high, low, close, volume,
                        quote_volume, trades, source)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
ON CONFLICT (symbol, timeframe, open_time) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
    volume = EXCLUDED.volume, quote_volume = EXCLUDED.quote_volume, trades = EXCLUDED.trades
"""


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


async def upsert_candles(pool: asyncpg.Pool, candles: Sequence[Candle], source: str) -> int:
    if not candles:
        return 0
    rows = [
        (
            c.symbol,
            c.timeframe,
            ms_to_dt(c.open_time_ms),
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
            c.quote_volume,
            c.trades,
            source,
        )
        for c in candles
    ]
    async with pool.acquire() as conn, conn.transaction():
        await conn.executemany(_UPSERT_CANDLE, rows)
    return len(rows)


async def insert_snapshots(
    pool: asyncpg.Pool, ts: datetime, snapshots: Sequence[SymbolSnapshot]
) -> int:
    rows = [
        (
            ts,
            s.symbol,
            s.stale,
            s.last_close,
            s.spread_bps,
            s.depth_bid_quote_1pct,
            s.depth_ask_quote_1pct,
            s.depth_truncated,
            s.slippage_buy_bps,
            s.slippage_sell_bps,
            s.ret_5m,
            s.ret_60m,
            s.return_z_1m,
            s.rel_volume_1m,
            s.realized_vol_1h,
            s.flags,
        )
        for s in snapshots
    ]
    await pool.executemany(
        "INSERT INTO q1.scanner_snapshots (ts, symbol, stale, last_close, spread_bps, "
        "depth_bid_1pct, depth_ask_1pct, depth_truncated, slippage_buy_bps, slippage_sell_bps, "
        "ret_5m, ret_60m, return_z_1m, rel_volume_1m, realized_vol_1h, flags) VALUES "
        "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) ON CONFLICT DO NOTHING",
        rows,
    )
    return len(rows)


async def load_tradable_instruments(pool: asyncpg.Pool, quote: str) -> list[Instrument]:
    rows = await pool.fetch(
        "SELECT * FROM q1.instruments WHERE quote = $1 AND status = 'TRADING' AND spot_allowed "
        "AND last_seen_at > now() - interval '1 day'",
        quote,
    )
    return [
        Instrument(
            symbol=r["symbol"],
            base=r["base"],
            quote=r["quote"],
            status=r["status"],
            tick_size=r["tick_size"],
            min_price=r["min_price"],
            max_price=r["max_price"],
            step_size=r["step_size"],
            min_qty=r["min_qty"],
            max_qty=r["max_qty"],
            min_notional=r["min_notional"],
            max_notional=r["max_notional"],
            order_types=tuple(r["order_types"]),
            spot_allowed=r["spot_allowed"],
            oco_allowed=r["oco_allowed"],
        )
        for r in rows
    ]
