"""Repositório de instrumentos. SQL parametrizado (asyncpg)."""

from __future__ import annotations

from collections.abc import Sequence

import asyncpg

from quantum_one.exchange.models import Instrument

_UPSERT = """
INSERT INTO q1.instruments (
    symbol, base, quote, status, tick_size, min_price, max_price, step_size,
    min_qty, max_qty, min_notional, max_notional, order_types, spot_allowed, oco_allowed
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
ON CONFLICT (symbol) DO UPDATE SET
    base = EXCLUDED.base, quote = EXCLUDED.quote, status = EXCLUDED.status,
    tick_size = EXCLUDED.tick_size, min_price = EXCLUDED.min_price,
    max_price = EXCLUDED.max_price, step_size = EXCLUDED.step_size,
    min_qty = EXCLUDED.min_qty, max_qty = EXCLUDED.max_qty,
    min_notional = EXCLUDED.min_notional, max_notional = EXCLUDED.max_notional,
    order_types = EXCLUDED.order_types, spot_allowed = EXCLUDED.spot_allowed,
    oco_allowed = EXCLUDED.oco_allowed, last_seen_at = now()
"""


async def upsert_instruments(pool: asyncpg.Pool, instruments: Sequence[Instrument]) -> int:
    rows = [
        (
            i.symbol,
            i.base,
            i.quote,
            i.status,
            i.tick_size,
            i.min_price,
            i.max_price,
            i.step_size,
            i.min_qty,
            i.max_qty,
            i.min_notional,
            i.max_notional,
            list(i.order_types),
            i.spot_allowed,
            i.oco_allowed,
        )
        for i in instruments
    ]
    async with pool.acquire() as conn, conn.transaction():
        await conn.executemany(_UPSERT, rows)
    return len(rows)


async def count_tradable(pool: asyncpg.Pool, quote: str) -> int:
    value = await pool.fetchval(
        "SELECT count(*) FROM q1.instruments WHERE quote = $1 AND status = 'TRADING' "
        "AND spot_allowed",
        quote,
    )
    return int(value)
