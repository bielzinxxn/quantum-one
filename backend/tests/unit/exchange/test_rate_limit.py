from __future__ import annotations

import pytest

from quantum_one.exchange.rate_limit import MemoryBanStore, RateLimitedError, WeightBudget


class FakeClock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def _budget(clock: FakeClock, limit: int = 100, ratio: float = 0.8) -> WeightBudget:
    return WeightBudget(MemoryBanStore(), limit, ratio, clock=clock, sleep=clock.sleep)


async def test_acquire_within_ceiling_does_not_wait() -> None:
    clock = FakeClock()
    b = _budget(clock)
    for _ in range(4):
        await b.acquire(20)
    assert b.used == 80 and clock.slept == []


async def test_exceeding_ceiling_waits_for_next_minute() -> None:
    clock = FakeClock(t=60 * 16_667 + 20.0)  # 20 s dentro do minuto
    b = _budget(clock)
    await b.acquire(80)
    await b.acquire(20)
    assert len(clock.slept) == 1 and 40 <= clock.slept[0] <= 41
    assert b.used == 20  # novo minuto


async def test_header_corrects_used_weight_upwards_only() -> None:
    b = _budget(FakeClock())
    await b.acquire(1)
    b.observe({"X-MBX-USED-WEIGHT-1M": "55"})
    assert b.used == 55
    b.observe({"x-mbx-used-weight-1m": "10"})
    assert b.used == 55
    b.observe({"X-MBX-USED-WEIGHT-1M": "lixo"})
    b.observe(None)
    assert b.used == 55


async def test_limit_from_exchange_info() -> None:
    b = _budget(FakeClock(), limit=100)
    b.set_limit(6000)
    assert b.ceiling == 4800
    b.set_limit(0)
    assert b.ceiling == 4800


async def test_429_retry_after_blocks_all_callers() -> None:
    clock = FakeClock()
    store = MemoryBanStore()
    b1 = WeightBudget(store, clock=clock, sleep=clock.sleep)
    b2 = WeightBudget(store, clock=clock, sleep=clock.sleep)  # outro processo, mesmo IP
    wait = await b1.on_rate_limited({"Retry-After": "30"}, banned=False)
    assert wait == 30
    with pytest.raises(RateLimitedError) as exc:
        await b2.acquire(1)
    assert 29 <= exc.value.wait_s <= 30
    clock.t += 31
    await b2.acquire(1)


async def test_418_without_header_uses_conservative_two_minutes() -> None:
    clock = FakeClock()
    b = _budget(clock)
    assert await b.on_rate_limited({}, banned=True) == 120
    assert await b.on_rate_limited(None, banned=False) == 60


async def test_refuses_instead_of_sleeping_too_long() -> None:
    clock = FakeClock(t=1_000_000.0)
    b = WeightBudget(MemoryBanStore(), 100, 0.8, max_wait_s=10, clock=clock, sleep=clock.sleep)
    await b.acquire(80)
    with pytest.raises(RateLimitedError, match="orçamento"):
        await b.acquire(1)
