"""Runtime comum a todos os workers.

Responsabilidades: logging, conexões (Postgres/Redis), loop de checagem de saúde,
servidor de saúde, watchdog e desligamento gracioso em SIGTERM/SIGINT.
O trabalho específico de cada serviço entra nas próximas fases via `ServiceSpec.work`.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from redis.asyncio import Redis

from quantum_one import __version__
from quantum_one.bus import redis_client
from quantum_one.core.config import Settings
from quantum_one.core.health import Check, HealthState, run_checks
from quantum_one.core.logging import configure_logging, get_logger
from quantum_one.core.watchdog import Watchdog
from quantum_one.db import pool as db_pool
from quantum_one.services import health_server


@dataclass
class ServiceContext:
    """O que o trabalho de um serviço recebe do runtime."""

    settings: Settings
    pool: asyncpg.Pool
    redis: Redis
    state: HealthState
    stop: asyncio.Event


Work = Callable[[ServiceContext], Coroutine[Any, Any, None]]


async def _idle(ctx: ServiceContext) -> None:
    await ctx.stop.wait()


async def sleep_or_stop(stop: asyncio.Event, seconds: float) -> bool:
    """Dorme até `seconds` ou até o desligamento. Retorna True se for para parar."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=max(0.0, seconds))
    return stop.is_set()


@dataclass
class ServiceSpec:
    name: str
    work: Work = _idle
    extra_health: dict[str, Any] = field(default_factory=dict)


async def _health_loop(
    state: HealthState, checks: dict[str, Check], interval_s: float, stop: asyncio.Event
) -> None:
    log = get_logger()
    previous_ready: bool | None = None
    while not stop.is_set():
        state.checks = await run_checks(checks, timeout_s=min(interval_s, 5.0))
        state.tick()
        if state.ready != previous_ready:
            log.info("readiness_changed", ready=state.ready, checks=state.snapshot()["checks"])
            previous_ready = state.ready
        await sleep_or_stop(stop, interval_s)


async def run_service(spec: ServiceSpec, settings: Settings) -> None:
    configure_logging(spec.name, settings.log_level, settings.secret_values)
    log = get_logger()
    log.info(
        "service_starting",
        version=__version__,
        env=settings.qone_env.value,
        trading_mode=settings.trading_mode.value,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    state = HealthState(service=spec.name, version=__version__, extra=dict(spec.extra_health))
    pool = await db_pool.create_pool(settings)
    redis = redis_client.create_redis(settings)
    checks: dict[str, Check] = {
        "postgres": lambda: db_pool.ping(pool),
        "redis": lambda: redis_client.ping(redis),
    }

    app = health_server.build_app(state, live_timeout_s=settings.health_check_interval_s * 3)
    runner = await health_server.start(app, settings.health_host, settings.health_port)
    watchdog = Watchdog(state.seconds_since_tick, settings.watchdog_timeout_s)
    watchdog.start()

    tasks = [
        asyncio.create_task(_health_loop(state, checks, settings.health_check_interval_s, stop)),
        asyncio.create_task(spec.work(ServiceContext(settings, pool, redis, state, stop))),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task.exception() is not None:
                raise task.exception()  # type: ignore[misc]
    finally:
        stop.set()
        log.info("service_stopping")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        watchdog.stop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
        await runner.cleanup()
        await redis.aclose()
        await pool.close()
        log.info("service_stopped")
