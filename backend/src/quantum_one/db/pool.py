"""Pool asyncpg. SQL sempre parametrizado; nunca montar consulta com f-string."""

from __future__ import annotations

import asyncpg

from quantum_one.core.config import Settings


async def create_pool(settings: Settings, min_size: int = 1, max_size: int = 5) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        min_size=min_size,
        max_size=max_size,
        command_timeout=10,
        server_settings={"application_name": settings.service_name, "timezone": "UTC"},
    )
    assert pool is not None
    return pool


async def ping(pool: asyncpg.Pool) -> None:
    value = await pool.fetchval("SELECT 1")
    if value != 1:
        raise RuntimeError("postgres ping inesperado")
