"""Trabalho do serviço `marketdata`: instrumentos (Fase 3) + Market Scanner (Fase 4)."""

from __future__ import annotations

import asyncio

from quantum_one.exchange.binance.client import build_exchange
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.rate_limit import RedisBanStore, WeightBudget
from quantum_one.services.instruments_sync import instruments_work
from quantum_one.services.runtime import ServiceContext
from quantum_one.services.scanner_service import ScannerService


async def scanner_work(ctx: ServiceContext) -> None:
    budget = WeightBudget(RedisBanStore(ctx.redis), ratio=ctx.settings.weight_budget_ratio)
    gateway = BinanceReadGateway(build_exchange(ctx.settings, authenticated=False), budget)
    try:
        await ScannerService(ctx, gateway).run()
    finally:
        await gateway.close()


async def marketdata_work(ctx: ServiceContext) -> None:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(instruments_work(ctx))
        tg.create_task(scanner_work(ctx))
