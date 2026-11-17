"""Trabalho do `marketdata` na Fase 3: relógio + sincronização de instrumentos (dado público)."""

from __future__ import annotations

from collections.abc import Callable

from quantum_one.core.logging import get_logger
from quantum_one.db.instruments import count_tradable, upsert_instruments
from quantum_one.exchange.binance.client import build_exchange
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.clock import measure_offset
from quantum_one.exchange.errors import classify
from quantum_one.exchange.rate_limit import RateLimitedError, RedisBanStore, WeightBudget
from quantum_one.services.exchange_status import ExchangeStatus
from quantum_one.services.runtime import ServiceContext, sleep_or_stop

RETRY_S = 30.0


def default_gateway(ctx: ServiceContext) -> BinanceReadGateway:
    budget = WeightBudget(RedisBanStore(ctx.redis), ratio=ctx.settings.weight_budget_ratio)
    return BinanceReadGateway(build_exchange(ctx.settings, authenticated=False), budget)


async def run_cycle(
    ctx: ServiceContext, gateway: BinanceReadGateway, status: ExchangeStatus
) -> None:
    reading = await measure_offset(gateway.server_time_ms)
    status.clock_offset_ms = round(reading.offset_ms, 1)
    if not reading.within(ctx.settings.clock_max_offset_ms):
        status.blocked([f"relógio fora da tolerância: {reading.offset_ms:.0f} ms"])
        return
    instruments, _ = await gateway.exchange_info()
    stored = await upsert_instruments(ctx.pool, instruments)
    status.ok(instruments=stored, tradable_usdt=await count_tradable(ctx.pool, "USDT"))


async def instruments_work(
    ctx: ServiceContext,
    make_gateway: Callable[[ServiceContext], BinanceReadGateway] = default_gateway,
) -> None:
    log = get_logger()
    status = ExchangeStatus()
    ctx.state.extra["exchange"] = status.as_dict()
    gateway = make_gateway(ctx)
    try:
        while not ctx.stop.is_set():
            wait = ctx.settings.instruments_sync_s
            try:
                await run_cycle(ctx, gateway, status)
                log.info("instruments_synced", **status.details, offset_ms=status.clock_offset_ms)
            except RateLimitedError as exc:
                status.state, status.last_error = "degraded", exc.reason
                wait = exc.wait_s
            except Exception as exc:  # classifica e tenta de novo
                err = classify(exc)
                status.failed(err)
                log.warning("instruments_sync_failed", kind=err.kind.value, code=err.code)
                wait = RETRY_S
            status.weight_used_1m = gateway.weight_used
            ctx.state.extra["exchange"] = status.as_dict()
            if await sleep_or_stop(ctx.stop, wait):
                break
    finally:
        await gateway.close()
