"""Envelope padrão de todo evento publicado nos Redis Streams."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from quantum_one.core.ids import uuid7


class Envelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid7)
    type: str = Field(min_length=1, max_length=64)
    schema_version: int = Field(default=1, ge=1)
    ts: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    source: str = Field(min_length=1, max_length=64)
    correlation_id: UUID | None = None
    payload: dict[str, Any]
