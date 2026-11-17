from __future__ import annotations

from decimal import Decimal as D

import pytest

from quantum_one.exchange.binance.filters import (
    floor_to_step,
    parse_instrument,
    validate_limit_order,
)
from tests.fakes.binance_payloads import BTCUSDT, ETHBTC_LEGACY


def test_parse_btcusdt_with_notional_filter() -> None:
    i = parse_instrument(BTCUSDT)
    assert (i.symbol, i.base, i.quote, i.status) == ("BTCUSDT", "BTC", "USDT", "TRADING")
    assert i.tick_size == D("0.01")
    assert i.step_size == D("0.00001")
    assert i.min_qty == D("0.00001")
    assert i.min_notional == D("5")
    assert i.max_notional == D("9000000")
    assert i.tradable and i.oco_allowed
    assert "LIMIT_MAKER" in i.order_types


def test_parse_legacy_min_notional_and_not_tradable() -> None:
    i = parse_instrument(ETHBTC_LEGACY)
    assert i.min_notional == D("0.0001")
    assert i.max_notional is None
    assert i.min_price == 0 and i.max_price == 0
    assert not i.tradable  # status BREAK


@pytest.mark.parametrize(
    ("value", "step", "expected"),
    [
        (D("0.123456"), D("0.001"), D("0.123")),
        (D("5"), D("2"), D("4")),
        (D("1.5"), D("0"), D("1.5")),
        (D("0.00099"), D("0.001"), D("0")),
    ],
)
def test_floor_to_step_never_rounds_up(value: D, step: D, expected: D) -> None:
    assert floor_to_step(value, step) == expected


def test_valid_order_passes() -> None:
    assert validate_limit_order(parse_instrument(BTCUSDT), D("60000.01"), D("0.001")) == []


@pytest.mark.parametrize(
    ("price", "qty", "fragment"),
    [
        (D("60000.015"), D("0.001"), "tickSize"),
        (D("60000"), D("0.0000123"), "stepSize"),
        (D("60000"), D("0.000001"), "minQty"),
        (D("100"), D("0.01"), "minNotional"),
        (D("0.001"), D("1"), "minPrice"),
        (D("2000000"), D("0.001"), "maxPrice"),
        (D("60000"), D("10000"), "maxQty"),
        (D("-1"), D("1"), "positivos"),
    ],
)
def test_filter_violations(price: D, qty: D, fragment: str) -> None:
    errors = validate_limit_order(parse_instrument(BTCUSDT), price, qty)
    assert any(fragment in e for e in errors), errors


def test_max_notional_violation() -> None:
    errors = validate_limit_order(parse_instrument(BTCUSDT), D("999999"), D("9000"))
    assert any("maxNotional" in e for e in errors)


def test_non_tradable_symbol_rejected() -> None:
    errors = validate_limit_order(parse_instrument(ETHBTC_LEGACY), D("0.05"), D("1"))
    assert any("não negociável" in e for e in errors)
