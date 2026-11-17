"""Orçamento de peso por IP (ADR-008 §4).

- Observa `X-MBX-USED-WEIGHT-1M` de cada resposta.
- Antes de cada requisição, se `usado + custo` passaria do teto (ratio × limite),
  espera a virada do minuto.
- Em 429/418 grava `banned_until` num store compartilhado (Redis), para que todos
  os processos no mesmo IP parem juntos.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Protocol

from redis.asyncio import Redis

BAN_KEY = "q1:exchange:binance:banned_until"
WEIGHT_HEADER = "x-mbx-used-weight-1m"


class BanStore(Protocol):
    async def get_banned_until(self) -> float: ...
    async def set_banned_until(self, epoch_s: float) -> None: ...


class MemoryBanStore:
    def __init__(self) -> None:
        self._until = 0.0

    async def get_banned_until(self) -> float:
        return self._until

    async def set_banned_until(self, epoch_s: float) -> None:
        self._until = max(self._until, epoch_s)


class RedisBanStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_banned_until(self) -> float:
        value = await self._redis.get(BAN_KEY)
        return float(value) if value else 0.0

    async def set_banned_until(self, epoch_s: float) -> None:
        current = await self.get_banned_until()
        if epoch_s > current:
            ttl = max(1, int(epoch_s - time.time()) + 1)
            await self._redis.set(BAN_KEY, str(epoch_s), ex=ttl)


class RateLimitedError(RuntimeError):
    """Levantado quando o orçamento proíbe a requisição (em vez de esperar)."""

    def __init__(self, wait_s: float, reason: str) -> None:
        super().__init__(f"{reason}: aguardar {wait_s:.1f}s")
        self.wait_s = wait_s
        self.reason = reason


class WeightBudget:
    def __init__(
        self,
        store: BanStore,
        limit_per_minute: int = 6000,
        ratio: float = 0.8,
        max_wait_s: float = 65.0,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], object] = asyncio.sleep,
    ) -> None:
        self._store = store
        self._limit = limit_per_minute
        self._ratio = ratio
        self._max_wait_s = max_wait_s
        self._clock = clock
        self._sleep = sleep
        self._used = 0
        self._minute = self._current_minute()

    def set_limit(self, limit_per_minute: int) -> None:
        """Limite autoritativo vem do exchangeInfo.rateLimits."""
        if limit_per_minute > 0:
            self._limit = limit_per_minute

    @property
    def ceiling(self) -> int:
        return int(self._limit * self._ratio)

    @property
    def used(self) -> int:
        self._roll()
        return self._used

    def _current_minute(self) -> int:
        return int(self._clock() // 60)

    def _roll(self) -> None:
        minute = self._current_minute()
        if minute != self._minute:
            self._minute, self._used = minute, 0

    async def acquire(self, cost: int) -> None:
        banned_until = await self._store.get_banned_until()
        now = self._clock()
        if banned_until > now:
            raise RateLimitedError(banned_until - now, "exchange em backoff/ban")
        self._roll()
        if self._used + cost > self.ceiling:
            wait = 60 - (now % 60) + 0.5
            if wait > self._max_wait_s:
                raise RateLimitedError(wait, "orçamento de peso esgotado")
            await self._sleep(wait)  # type: ignore[misc]
            self._roll()
        self._used += cost  # reserva otimista; o cabeçalho corrige depois

    def observe(self, headers: Mapping[str, str] | None) -> None:
        if not headers:
            return
        for key, value in headers.items():
            if key.lower() == WEIGHT_HEADER:
                try:
                    reported = int(value)
                except ValueError:
                    return
                self._roll()
                self._used = max(self._used, reported)
                return

    async def on_rate_limited(self, headers: Mapping[str, str] | None, banned: bool) -> float:
        """Registra backoff a partir do Retry-After (segundos). Retorna o tempo de espera."""
        retry_after = None
        for key, value in (headers or {}).items():
            if key.lower() == "retry-after":
                try:
                    retry_after = float(value)
                except ValueError:
                    retry_after = None
        # sem cabeçalho: conservador (ban mínimo documentado é 2 min)
        wait = retry_after if retry_after is not None else (120.0 if banned else 60.0)
        await self._store.set_banned_until(self._clock() + wait)
        return wait
