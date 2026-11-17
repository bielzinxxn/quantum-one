"""Runtime real: o serviço sobe, fica pronto com Postgres+Redis e desliga limpo."""

from __future__ import annotations

import asyncio
import json
import socket
import urllib.error
import urllib.request
from typing import Any

import pytest

from quantum_one.services.runtime import ServiceContext, ServiceSpec, run_service

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _get(url: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


async def test_service_becomes_ready_and_stops_cleanly(settings_for: Any) -> None:
    port = _free_port()
    settings = settings_for("q1_trader").model_copy(
        update={"health_host": "127.0.0.1", "health_port": port, "health_check_interval_s": 0.2}
    )
    observed: dict[str, Any] = {}

    async def work(ctx: ServiceContext) -> None:
        state = ctx.state
        for _ in range(100):
            if state.ready:
                break
            await asyncio.sleep(0.05)
        observed["status"], observed["body"] = await asyncio.to_thread(
            _get, f"http://127.0.0.1:{port}/health/ready"
        )
        # retornar encerra o serviço (FIRST_COMPLETED)

    spec = ServiceSpec(name="trader", work=work, extra_health={"trading_state": "BLOCKED"})
    await asyncio.wait_for(run_service(spec, settings), timeout=20)

    assert observed["status"] == 200
    assert observed["body"]["checks"]["postgres"]["ok"]
    assert observed["body"]["checks"]["redis"]["ok"]
    assert observed["body"]["trading_state"] == "BLOCKED"
    with pytest.raises(urllib.error.URLError):  # servidor de saúde foi fechado
        await asyncio.to_thread(
            urllib.request.urlopen, f"http://127.0.0.1:{port}/health/live", None, 1
        )


async def test_service_not_ready_when_redis_password_wrong(settings_for: Any) -> None:
    port = _free_port()
    settings = settings_for("q1_engine").model_copy(
        update={
            "health_host": "127.0.0.1",
            "health_port": port,
            "health_check_interval_s": 0.2,
            "redis_password": settings_for("q1_engine").postgres_password,  # senha errada
        }
    )
    observed: dict[str, Any] = {}

    async def work(ctx: ServiceContext) -> None:
        await asyncio.sleep(1.0)
        observed["status"], observed["body"] = await asyncio.to_thread(
            _get, f"http://127.0.0.1:{port}/health/ready"
        )

    await asyncio.wait_for(run_service(ServiceSpec(name="engine", work=work), settings), timeout=20)
    assert observed["status"] == 503
    assert observed["body"]["checks"]["postgres"]["ok"] is True
    assert observed["body"]["checks"]["redis"]["ok"] is False
