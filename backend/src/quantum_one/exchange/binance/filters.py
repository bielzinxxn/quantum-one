"""Filtros de símbolo (filters.md) → `Instrument` e validação de ordens.

Regras (doc oficial): valor 0 desativa minPrice/maxPrice/tickSize; preço deve ser
múltiplo de tickSize; quantidade múltipla de stepSize; notional = preço × quantidade.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Any

from quantum_one.exchange.models import Instrument

ZERO = Decimal(0)


def _d(value: Any, default: str = "0") -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(default)


def parse_instrument(raw: dict[str, Any]) -> Instrument:
    filters = {f["filterType"]: f for f in raw.get("filters", [])}
    price = filters.get("PRICE_FILTER", {})
    lot = filters.get("LOT_SIZE", {})
    notional = filters.get("NOTIONAL")
    legacy = filters.get("MIN_NOTIONAL")
    if notional is not None:
        min_notional = _d(notional.get("minNotional"))
        max_notional: Decimal | None = _d(notional.get("maxNotional"))
    else:
        min_notional = _d(legacy.get("minNotional")) if legacy else ZERO
        max_notional = None
    return Instrument(
        symbol=raw["symbol"],
        base=raw["baseAsset"],
        quote=raw["quoteAsset"],
        status=raw["status"],
        tick_size=_d(price.get("tickSize")),
        min_price=_d(price.get("minPrice")),
        max_price=_d(price.get("maxPrice")),
        step_size=_d(lot.get("stepSize")),
        min_qty=_d(lot.get("minQty")),
        max_qty=_d(lot.get("maxQty")),
        min_notional=min_notional,
        max_notional=max_notional,
        order_types=tuple(raw.get("orderTypes", [])),
        spot_allowed=bool(raw.get("isSpotTradingAllowed", False)),
        oco_allowed=bool(raw.get("ocoAllowed", False)),
    )


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    """Arredonda PARA BAIXO ao múltiplo de `step` (nunca excede o pedido)."""
    if step <= ZERO:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def validate_limit_order(inst: Instrument, price: Decimal, qty: Decimal) -> list[str]:
    """Violações de PRICE_FILTER, LOT_SIZE e NOTIONAL para uma ordem LIMIT."""
    errors: list[str] = []
    if not inst.tradable:
        errors.append(f"símbolo não negociável (status={inst.status})")
    if price <= ZERO or qty <= ZERO:
        errors.append("preço e quantidade devem ser positivos")
        return errors
    if inst.min_price > ZERO and price < inst.min_price:
        errors.append(f"preço {price} < minPrice {inst.min_price}")
    if inst.max_price > ZERO and price > inst.max_price:
        errors.append(f"preço {price} > maxPrice {inst.max_price}")
    if inst.tick_size > ZERO and price % inst.tick_size != ZERO:
        errors.append(f"preço {price} não é múltiplo de tickSize {inst.tick_size}")
    if qty < inst.min_qty:
        errors.append(f"quantidade {qty} < minQty {inst.min_qty}")
    if inst.max_qty > ZERO and qty > inst.max_qty:
        errors.append(f"quantidade {qty} > maxQty {inst.max_qty}")
    if inst.step_size > ZERO and qty % inst.step_size != ZERO:
        errors.append(f"quantidade {qty} não é múltiplo de stepSize {inst.step_size}")
    notional = price * qty
    if notional < inst.min_notional:
        errors.append(f"notional {notional} < minNotional {inst.min_notional}")
    if inst.max_notional is not None and inst.max_notional > ZERO and notional > inst.max_notional:
        errors.append(f"notional {notional} > maxNotional {inst.max_notional}")
    return errors
