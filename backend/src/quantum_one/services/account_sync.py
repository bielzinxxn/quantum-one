"""Trabalho do `trader` na Fase 3: política da chave, relógio e leitura da conta.

O trader continua `BLOCKED` independentemente do resultado: só a reconciliação
da Fase 8 poderá liberar operações. Aqui ele apenas lê e registra.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from quantum_one.core.config import Environment
from quantum_one.core.logging import get_logger
from quantum_one.db.accounts import insert_account_snapshot
from quantum_one.exchange import key_policy
from quantum_one.exchange.binance.client import build_exchange
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.clock import measure_offset
from quantum_one.exchange.errors import ErrorKind, classify
from quantum_one.exchange.rate_limit import RateLimitedError, RedisBanStore, WeightBudget
from quantum_one.services.exchange_status import ExchangeStatus
from quantum_one.services.runtime import ServiceContext, sleep_or_stop

RETRY_S = 30.0
BLOCKED_RETRY_S = 300.0
KEY_RECHECK_S = 600.0


class KeyPolicyViolation(RuntimeError):
    pass


async def check_key(ctx: ServiceContext, gateway: BinanceReadGateway) -> None:
    perms = await gateway.key_permissions()
    violations = key_policy.evaluate(
        perms,
        ctx.settings.binance_key_policy,
        require_ip_restrict=ctx.settings.qone_env is Environment.PROD,
    )
    if violations:
        raise KeyPolicyViolation("; ".join(violations))


async def sync_account(
    ctx: ServiceContext, gateway: BinanceReadGateway, status: ExchangeStatus
) -> bool:
    """Um ciclo de leitura. Retorna False se ficou bloqueado (relógio)."""
    reading = await measure_offset(gateway.server_time_ms)
    status.clock_offset_ms = round(reading.offset_ms, 1)
    if not reading.within(ctx.settings.clock_max_offset_ms):
        status.blocked([f"relógio fora da tolerância: {reading.offset_ms:.0f} ms"])
        return False
    snapshot = await gateway.account()
    orders = await gateway.open_orders()
    await insert_account_snapshot(ctx.pool, snapshot, open_orders=len(orders))
    status.ok(assets=len(snapshot.balances), open_orders=len(orders), can_trade=snapshot.can_trade)
    return True


GatewayFactory = Callable[[ServiceContext], BinanceReadGateway]


def default_gateway(ctx: ServiceContext) -> BinanceReadGateway:
    budget = WeightBudget(RedisBanStore(ctx.redis), ratio=ctx.settings.weight_budget_ratio)
    return BinanceReadGateway(build_exchange(ctx.settings, authenticated=True), budget)


async def account_work(ctx: ServiceContext, make_gateway: GatewayFactory = default_gateway) -> None:
    log = get_logger()
    status = ExchangeStatus()
    ctx.state.extra["trading_state"] = "BLOCKED"
    if not ctx.settings.has_binance_credentials:
        status.state = "credentials_missing"
        ctx.state.extra["exchange"] = status.as_dict()
        log.warning("binance_credentials_missing")
        await ctx.stop.wait()
        return

    gateway = make_gateway(ctx)
    key_checked_at = 0.0
    try:
        while not ctx.stop.is_set():
            wait = ctx.settings.account_poll_s
            try:
                if time.monotonic() - key_checked_at > KEY_RECHECK_S:
                    await check_key(ctx, gateway)
                    key_checked_at = time.monotonic()
                await sync_account(ctx, gateway, status)
            except KeyPolicyViolation as exc:
                status.blocked(str(exc).split("; "))
                log.error("binance_key_policy_violation", violations=status.reasons)
                key_checked_at, wait = 0.0, BLOCKED_RETRY_S
            except RateLimitedError as exc:
                status.state, status.last_error = "degraded", exc.reason
                wait = exc.wait_s
            except Exception as exc:  # classifica; nunca derruba o processo
                err = classify(exc)
                status.failed(err)
                log.warning("account_sync_failed", kind=err.kind.value, code=err.code)
                if err.kind in (ErrorKind.AUTH, ErrorKind.CLOCK):
                    key_checked_at, wait = 0.0, BLOCKED_RETRY_S
                else:
                    wait = RETRY_S
            status.weight_used_1m = gateway.weight_used
            ctx.state.extra["exchange"] = status.as_dict()
            if await sleep_or_stop(ctx.stop, wait):
                break
    finally:
        await gateway.close()
