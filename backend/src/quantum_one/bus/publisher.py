"""Publicação de eventos em Redis Streams (XADD com retenção aproximada)."""

from __future__ import annotations

from redis.asyncio import Redis

from quantum_one.contracts.envelope import Envelope

DEFAULT_MAXLEN = {"md:candles": 200_000, "md:scanner": 20_000, "md:health": 5_000}


class StreamPublisher:
    def __init__(self, redis: Redis, source: str) -> None:
        self._redis = redis
        self._source = source

    async def publish(self, stream: str, event_type: str, payload: dict[str, object]) -> str:
        env = Envelope(type=event_type, source=self._source, payload=payload)
        maxlen = DEFAULT_MAXLEN.get(stream, 10_000)
        entry_id = await self._redis.xadd(
            stream, {"data": env.model_dump_json()}, maxlen=maxlen, approximate=True
        )
        return entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
