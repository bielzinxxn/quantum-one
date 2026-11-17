"""Estado de saúde de um serviço: liveness (processo vivo) e readiness (dependências OK)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

Check = Callable[[], Awaitable[None]]


@dataclass
class CheckResult:
    ok: bool
    detail: str = ""
    latency_ms: float = 0.0


@dataclass
class HealthState:
    service: str
    version: str
    checks: dict[str, CheckResult] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    last_tick: float = field(default_factory=time.monotonic)
    started_at: float = field(default_factory=time.time)

    def tick(self) -> None:
        self.last_tick = time.monotonic()

    def seconds_since_tick(self) -> float:
        return time.monotonic() - self.last_tick

    @property
    def ready(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks.values())

    def snapshot(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "version": self.version,
            "ready": self.ready,
            "uptime_s": round(time.time() - self.started_at, 1),
            "checks": {
                name: {"ok": r.ok, "detail": r.detail, "latency_ms": round(r.latency_ms, 1)}
                for name, r in self.checks.items()
            },
            **self.extra,
        }


async def run_checks(checks: Mapping[str, Check], timeout_s: float) -> dict[str, CheckResult]:
    """Executa todas as checagens em paralelo, cada uma com timeout."""

    async def one(check: Check) -> CheckResult:
        start = time.perf_counter()
        try:
            await asyncio.wait_for(check(), timeout=timeout_s)
        except TimeoutError:
            return CheckResult(False, "timeout", (time.perf_counter() - start) * 1000)
        except Exception as exc:
            return CheckResult(False, type(exc).__name__, (time.perf_counter() - start) * 1000)
        return CheckResult(True, "ok", (time.perf_counter() - start) * 1000)

    names = list(checks)
    results = await asyncio.gather(*(one(checks[n]) for n in names))
    return dict(zip(names, results, strict=True))
