from __future__ import annotations

import asyncio
import socket

import pytest
from aiohttp.test_utils import TestClient, TestServer

from quantum_one.core.health import CheckResult, HealthState
from quantum_one.services import health_server, healthcheck


async def _client(state: HealthState) -> TestClient:  # type: ignore[type-arg]
    client = TestClient(TestServer(health_server.build_app(state, live_timeout_s=10)))
    await client.start_server()
    return client


async def test_live_ok_and_stale() -> None:
    state = HealthState("engine", "0")
    client = await _client(state)
    try:
        assert (await client.get("/health/live")).status == 200
        state.last_tick -= 100
        resp = await client.get("/health/live")
        assert resp.status == 503
        assert (await resp.json())["alive"] is False
    finally:
        await client.close()


async def test_ready_reflects_checks() -> None:
    state = HealthState("trader", "0", extra={"trading_state": "BLOCKED"})
    client = await _client(state)
    try:
        assert (await client.get("/health/ready")).status == 503
        state.checks = {"postgres": CheckResult(True), "redis": CheckResult(True)}
        resp = await client.get("/health/ready")
        body = await resp.json()
        assert resp.status == 200
        assert body["ready"] is True
        assert body["trading_state"] == "BLOCKED"
    finally:
        await client.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def test_docker_healthcheck_cli() -> None:
    state = HealthState("engine", "0")
    port = _free_port()
    runner = await health_server.start(health_server.build_app(state, 10), "127.0.0.1", port)
    try:
        url = f"http://127.0.0.1:{port}"
        assert await asyncio.to_thread(healthcheck.check, url + "/health/live")
        assert not await asyncio.to_thread(healthcheck.check, url + "/health/ready")
    finally:
        await runner.cleanup()
    assert not await asyncio.to_thread(
        healthcheck.check, f"http://127.0.0.1:{port}/health/live", 0.5
    )


def test_healthcheck_main_uses_env_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEALTH_PORT", str(_free_port()))
    assert healthcheck.main([]) == 1  # nada escutando → falha
