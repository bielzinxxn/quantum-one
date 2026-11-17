"""Cliente Redis assíncrono."""

from __future__ import annotations

from redis.asyncio import Redis

from quantum_one.core.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password.get_secret_value(),
        socket_timeout=5,
        socket_connect_timeout=5,
        health_check_interval=30,
        decode_responses=True,
        client_name=settings.service_name,
    )


async def ping(redis: Redis) -> None:
    if not await redis.ping():
        raise RuntimeError("redis ping falhou")
