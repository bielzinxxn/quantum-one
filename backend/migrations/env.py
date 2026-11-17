"""Ambiente Alembic assíncrono. Roda como papel `q1_migrator` (dono do schema `q1`)."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import URL, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from quantum_one.core.config import load_settings

SCHEMA = "q1"


def _url() -> URL:
    s = load_settings()
    return URL.create(
        "postgresql+asyncpg",
        username=s.postgres_user,
        password=s.postgres_password.get_secret_value(),
        host=s.postgres_host,
        port=s.postgres_port,
        database=s.postgres_db,
    )


def _do_run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table_schema=SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = async_engine_from_config(
        {"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with engine.connect() as conn:
        await conn.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("modo offline não suportado: rode contra o banco")
asyncio.run(_run_online())
