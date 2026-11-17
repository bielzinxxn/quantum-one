"""Redis: autenticação obrigatória, comandos perigosos desabilitados, persistência."""

from __future__ import annotations

from typing import Any

import pytest
from redis.asyncio import Redis
from redis.exceptions import AuthenticationError, ResponseError

from quantum_one.bus.redis_client import create_redis, ping

pytestmark = pytest.mark.integration


async def test_auth_required(settings_for: Any) -> None:
    s = settings_for("q1_engine")
    anon = Redis(host=s.redis_host, port=s.redis_port)
    try:
        with pytest.raises((AuthenticationError, ResponseError)):
            await anon.set("x", "1")
    finally:
        await anon.aclose()


async def test_authenticated_ping_and_stream_roundtrip(settings_for: Any) -> None:
    r = create_redis(settings_for("q1_engine"))
    try:
        await ping(r)
        eid = await r.xadd("it:stream", {"k": "v"}, maxlen=10, approximate=False)
        entries = await r.xrange("it:stream", min=eid, max=eid)
        assert entries[0][1] == {"k": "v"}
        await r.delete("it:stream")
    finally:
        await r.aclose()


@pytest.mark.parametrize(
    "command", ["FLUSHALL", "FLUSHDB", "CONFIG GET *", "KEYS *", "DEBUG SLEEP 0"]
)
async def test_dangerous_commands_disabled(settings_for: Any, command: str) -> None:
    r = create_redis(settings_for("q1_engine"))
    try:
        with pytest.raises(ResponseError, match="unknown command"):
            await r.execute_command(*command.split())
    finally:
        await r.aclose()


async def test_persistence_and_no_eviction(settings_for: Any) -> None:
    r = create_redis(settings_for("q1_engine"))
    try:
        assert (await r.info("persistence"))["aof_enabled"] == 1
        assert (await r.info("memory"))["maxmemory_policy"] == "noeviction"
    finally:
        await r.aclose()
