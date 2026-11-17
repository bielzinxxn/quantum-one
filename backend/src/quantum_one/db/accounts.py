"""Repositório de snapshots de conta e saldo (fonte: exchange)."""

from __future__ import annotations

import asyncpg

from quantum_one.exchange.models import AccountSnapshot


async def insert_account_snapshot(
    pool: asyncpg.Pool, snap: AccountSnapshot, open_orders: int
) -> int:
    async with pool.acquire() as conn, conn.transaction():
        snapshot_id: int = await conn.fetchval(
            "INSERT INTO q1.account_snapshots (taken_at, source, account_type, can_trade, "
            "maker_commission, taker_commission, open_orders) "
            "VALUES ($1, 'exchange', $2, $3, $4, $5, $6) RETURNING id",
            snap.taken_at,
            snap.account_type,
            snap.can_trade,
            snap.maker_commission,
            snap.taker_commission,
            open_orders,
        )
        await conn.executemany(
            "INSERT INTO q1.balance_snapshots (snapshot_id, asset, free, locked) "
            "VALUES ($1, $2, $3, $4)",
            [(snapshot_id, b.asset, b.free, b.locked) for b in snap.balances],
        )
    return snapshot_id
