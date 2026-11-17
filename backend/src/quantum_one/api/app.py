"""Aplicação FastAPI. Na Fase 2 expõe apenas saúde; auth e rotas vêm nas fases 10/12."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from quantum_one import __version__
from quantum_one.bus import redis_client
from quantum_one.core.config import Settings
from quantum_one.core.health import Check, HealthState, run_checks
from quantum_one.core.logging import configure_logging
from quantum_one.db import pool as db_pool


def create_app(settings: Settings, checks: dict[str, Check] | None = None) -> FastAPI:
    state = HealthState(service="api", version=__version__)
    deps: dict[str, Check] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging("api", settings.log_level, settings.secret_values)
        if checks is not None:
            deps.update(checks)
            yield
            return
        pool = await db_pool.create_pool(settings, max_size=10)
        redis = redis_client.create_redis(settings)
        deps.update(
            {
                "postgres": lambda: db_pool.ping(pool),
                "redis": lambda: redis_client.ping(redis),
            }
        )
        try:
            yield
        finally:
            await redis.aclose()
            await pool.close()

    app = FastAPI(
        title="QUANTUM ONE API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,  # sem Swagger público; reabilitar só em dev se necessário
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health/live")
    async def live() -> dict[str, object]:
        return {"service": "api", "alive": True}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        state.checks = await run_checks(deps, timeout_s=3.0)
        return JSONResponse(state.snapshot(), status_code=200 if state.ready else 503)

    return app
