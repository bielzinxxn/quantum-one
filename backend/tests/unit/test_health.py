from __future__ import annotations

import asyncio

from quantum_one.core.health import CheckResult, HealthState, run_checks


async def _ok() -> None:
    return None


async def _boom() -> None:
    raise ConnectionError("down")


async def _slow() -> None:
    await asyncio.sleep(5)


async def test_run_checks_mixed_results() -> None:
    results = await run_checks({"ok": _ok, "boom": _boom, "slow": _slow}, timeout_s=0.1)
    assert results["ok"].ok
    assert not results["boom"].ok and results["boom"].detail == "ConnectionError"
    assert not results["slow"].ok and results["slow"].detail == "timeout"


def test_not_ready_without_checks() -> None:
    assert not HealthState("x", "0").ready


def test_ready_only_if_all_ok() -> None:
    s = HealthState("x", "0")
    s.checks = {"a": CheckResult(True), "b": CheckResult(False, "down")}
    assert not s.ready
    s.checks["b"] = CheckResult(True)
    assert s.ready


def test_snapshot_shape_and_extra() -> None:
    s = HealthState("trader", "0.2.0", extra={"trading_state": "BLOCKED"})
    s.checks = {"postgres": CheckResult(True, "ok", 1.234)}
    snap = s.snapshot()
    assert snap["service"] == "trader"
    assert snap["trading_state"] == "BLOCKED"
    assert snap["checks"]["postgres"] == {"ok": True, "detail": "ok", "latency_ms": 1.2}


def test_tick_resets_staleness() -> None:
    s = HealthState("x", "0")
    s.last_tick -= 100
    assert s.seconds_since_tick() >= 100
    s.tick()
    assert s.seconds_since_tick() < 1
