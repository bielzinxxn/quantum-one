from __future__ import annotations

from datetime import UTC
from decimal import Decimal as D

from quantum_one.exchange.binance import parsers
from tests.fakes import binance_payloads as P


def test_rate_limits_and_weight_limit() -> None:
    limits = parsers.parse_rate_limits(P.EXCHANGE_INFO["rateLimits"])
    assert {(r.kind, r.interval_seconds, r.limit) for r in limits} >= {
        ("REQUEST_WEIGHT", 60, 6000),
        ("ORDERS", 10, 50),
        ("RAW_REQUESTS", 300, 61000),
    }
    assert parsers.weight_limit_per_minute(limits) == 6000
    assert parsers.weight_limit_per_minute([]) is None


def test_account_keeps_decimal_precision_and_drops_zero_balances() -> None:
    snap = parsers.parse_account(P.ACCOUNT)
    by_asset = {b.asset: b for b in snap.balances}
    assert set(by_asset) == {"BTC", "USDT"}
    assert by_asset["USDT"].free == D("1500.12345678")
    assert by_asset["USDT"].total == D("1750.12345678")
    assert isinstance(by_asset["BTC"].free, D)
    assert snap.can_trade and snap.account_type == "SPOT"
    assert snap.maker_commission == D("0.001")
    assert snap.taken_at.tzinfo is UTC


def test_open_order() -> None:
    (o,) = [parsers.parse_open_order(x) for x in P.OPEN_ORDERS]
    assert o.order_id == 1 and o.client_order_id == "myOrder1"
    assert o.price == D("60000.01") and o.orig_qty == D("0.001")
    assert o.created_at.year == 2017


def test_trade() -> None:
    (t,) = [parsers.parse_trade(x) for x in P.MY_TRADES]
    assert t.trade_id == 28457 and t.order_id == 100234
    assert t.quote_qty == D("60.0001")
    assert t.commission_asset == "BNB" and t.is_buyer and not t.is_maker


def test_commission_effective_and_bnb_discount() -> None:
    c = parsers.parse_commission(P.COMMISSION)
    assert c.effective(maker=True) == D("0.001")
    assert c.effective(maker=False) == D("0.001")
    assert c.bnb_discount_enabled
    assert c.bnb_discount_multiplier == D("0.75")


def test_key_permissions_complete() -> None:
    k = parsers.parse_key_permissions(P.KEY_READ_ONLY)
    assert k.enable_reading and k.ip_restrict
    assert not k.enable_withdrawals and not k.enable_spot_and_margin_trading
    assert "createTime" in k.raw_unknown


def test_missing_permission_fields_are_fail_closed() -> None:
    k = parsers.parse_key_permissions({})
    assert not k.enable_reading and not k.ip_restrict
    assert k.enable_withdrawals and k.enable_futures and k.enable_spot_and_margin_trading
