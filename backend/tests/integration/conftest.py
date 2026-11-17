"""Integração contra a stack dev (docker-compose.dev.yml). Senhas vêm do .env carregado
pelo `make test-integration`; os testes são pulados se o ambiente não estiver pronto."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

import asyncpg
import pytest

from quantum_one.core.config import Settings

ROLE_PASSWORD_VAR = {
    "q1_migrator": "PG_MIGRATOR_PASSWORD",
    "q1_marketdata": "PG_MARKETDATA_PASSWORD",
    "q1_engine": "PG_ENGINE_PASSWORD",
    "q1_trader": "PG_TRADER_PASSWORD",
    "q1_accounting": "PG_ACCOUNTING_PASSWORD",
    "q1_api": "PG_API_PASSWORD",
}


def _require(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        pytest.skip(f"{var} ausente — rode `make test-integration`")
    return value


@pytest.fixture
def settings_for() -> Callable[[str], Settings]:
    def build(role: str) -> Settings:
        return Settings(
            qone_env="test",
            service_name=f"it-{role}",
            postgres_host="127.0.0.1",
            postgres_port=int(os.environ.get("DEV_PG_PORT", "55432")),
            postgres_db=os.environ.get("POSTGRES_DB", "quantum_one"),
            postgres_user=role,
            postgres_password=_require(ROLE_PASSWORD_VAR[role]),
            redis_host="127.0.0.1",
            redis_port=int(os.environ.get("DEV_REDIS_PORT", "56379")),
            redis_password=_require("REDIS_PASSWORD"),
        )

    return build


@pytest.fixture
def connect(
    settings_for: Callable[[str], Settings],
) -> Callable[[str], AsyncIterator[asyncpg.Connection]]:
    async def _connect(role: str) -> asyncpg.Connection:
        s = settings_for(role)
        return await asyncpg.connect(
            host=s.postgres_host,
            port=s.postgres_port,
            database=s.postgres_db,
            user=s.postgres_user,
            password=s.postgres_password.get_secret_value(),
        )

    return _connect  # type: ignore[return-value]
