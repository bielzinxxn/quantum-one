"""Estado da conexão com a exchange, exposto no /health/ready (campo `exchange`)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from quantum_one.exchange.errors import ClassifiedError


@dataclass
class ExchangeStatus:
    state: str = "starting"  # starting | ok | degraded | blocked | credentials_missing
    reasons: list[str] = field(default_factory=list)
    clock_offset_ms: float | None = None
    weight_used_1m: int | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def ok(self, **details: Any) -> None:
        self.state, self.reasons, self.last_error = "ok", [], None
        self.last_success_at = datetime.now(tz=UTC).isoformat()
        self.details.update(details)

    def blocked(self, reasons: list[str]) -> None:
        self.state, self.reasons = "blocked", reasons

    def failed(self, err: ClassifiedError) -> None:
        # credencial/relógio bloqueiam; o resto degrada e será tentado de novo
        self.state = "blocked" if err.kind.value in ("auth", "clock") else "degraded"
        self.last_error = f"{err.kind.value}:{err.code}" if err.code else err.kind.value
        self.reasons = [err.message[:200]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
