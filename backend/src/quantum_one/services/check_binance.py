"""Diagnóstico da conexão com a Binance (somente leitura).

Uso na VPS:  make check-binance
Códigos de saída: 0 ok · 1 erro de conexão/API · 2 política da chave violada ·
3 sem credenciais (só checagens públicas) · 4 relógio fora da tolerância · 78 config inválida
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from decimal import Decimal

from pydantic import ValidationError

from quantum_one.core.config import Environment, Settings, load_settings
from quantum_one.exchange import key_policy
from quantum_one.exchange.binance.client import build_exchange, key_type
from quantum_one.exchange.binance.gateway import BinanceReadGateway
from quantum_one.exchange.clock import measure_offset
from quantum_one.exchange.errors import classify
from quantum_one.exchange.rate_limit import MemoryBanStore, WeightBudget

Out = Callable[[str], None]


def _fmt(d: Decimal) -> str:
    return f"{d.normalize():f}"


async def run_checks(
    settings: Settings, out: Out, gateway: BinanceReadGateway | None = None
) -> int:
    authenticated = settings.has_binance_credentials
    budget = WeightBudget(MemoryBanStore(), ratio=settings.weight_budget_ratio)
    gw = gateway or BinanceReadGateway(
        build_exchange(settings, authenticated=authenticated), budget
    )
    try:
        out(
            f"ambiente: {settings.qone_env.value} · testnet: {settings.binance_testnet} · "
            f"política da chave: {settings.binance_key_policy.value}"
        )

        reading = await measure_offset(gw.server_time_ms)
        clock_ok = reading.within(settings.clock_max_offset_ms)
        out(
            f"[{'OK' if clock_ok else 'FALHA'}] relógio: offset {reading.offset_ms:+.0f} ms, "
            f"RTT {reading.rtt_ms:.0f} ms (tolerância {settings.clock_max_offset_ms} ms)"
        )

        instruments, limits = await gw.exchange_info()
        usdt = [i for i in instruments if i.quote == "USDT" and i.tradable]
        out(f"[OK] exchangeInfo: {len(instruments)} símbolos, {len(usdt)} USDT negociáveis")
        for lim in limits:
            out(f"     limite {lim.kind}: {lim.limit} / {lim.interval_seconds}s")

        if not clock_ok:
            return 4
        if not authenticated:
            out("[--] sem credenciais: checagens privadas puladas (preencha BINANCE_API_*)")
            return 3

        assert settings.binance_api_secret is not None
        ktype = key_type(settings.binance_api_secret.get_secret_value())
        out(f"     tipo de chave: {ktype}")
        if ktype == "hmac":
            out("[AVISO] a Binance declara chaves HMAC depreciadas; migre para Ed25519")
        perms = await gw.key_permissions()
        violations = key_policy.evaluate(
            perms,
            settings.binance_key_policy,
            require_ip_restrict=settings.qone_env is Environment.PROD,
        )
        out(
            f"     permissões: leitura={perms.enable_reading} "
            f"trading={perms.enable_spot_and_margin_trading} saque={perms.enable_withdrawals} "
            f"restrição_IP={perms.ip_restrict}"
        )
        if violations:
            for v in violations:
                out(f"[FALHA] chave: {v}")
            return 2
        out("[OK] política da chave atendida")

        account = await gw.account()
        out(
            f"[OK] conta {account.account_type}: {len(account.balances)} ativos com saldo, "
            f"canTrade={account.can_trade}"
        )
        for b in sorted(account.balances, key=lambda b: b.asset):
            out(f"     {b.asset:<8} livre {_fmt(b.free):>20}  travado {_fmt(b.locked):>20}")

        orders = await gw.open_orders()
        out(f"[OK] ordens abertas: {len(orders)}")

        comm = await gw.commission("BTCUSDT")
        bnb = (
            f"ativo ×{_fmt(comm.bnb_discount_multiplier)}"
            if comm.bnb_discount_enabled
            else "inativo"
        )
        out(
            f"[OK] comissão BTCUSDT: maker {_fmt(comm.effective(maker=True))} · "
            f"taker {_fmt(comm.effective(maker=False))} · desconto BNB {bnb}"
        )
        out(f"     peso usado no minuto: {budget.used} (teto {budget.ceiling})")
        return 0
    except Exception as exc:  # diagnóstico: reportar e sair
        err = classify(exc)
        out(f"[FALHA] {err.kind.value} (código {err.code}): {err.message}")
        return 1
    finally:
        await gw.close()


def main() -> int:
    try:
        settings = load_settings()
    except ValidationError as exc:
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"]) or "config"
            sys.stderr.write(f"config inválida: {field}: {err['msg']}\n")
        return 78
    return asyncio.run(run_checks(settings, print))


if __name__ == "__main__":
    raise SystemExit(main())
