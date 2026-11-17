from __future__ import annotations

import dataclasses

import pytest

from quantum_one.core.config import KeyPolicy
from quantum_one.exchange.binance.parsers import parse_key_permissions
from quantum_one.exchange.key_policy import evaluate
from tests.fakes.binance_payloads import KEY_READ_ONLY

BASE = parse_key_permissions(KEY_READ_ONLY)


def test_read_only_key_approved() -> None:
    assert evaluate(BASE, KeyPolicy.READ_ONLY, require_ip_restrict=True) == []


@pytest.mark.parametrize(
    "attr",
    [
        "enable_withdrawals",
        "enable_internal_transfer",
        "permits_universal_transfer",
        "enable_margin",
        "enable_futures",
        "enable_vanilla_options",
        "enable_portfolio_margin_trading",
    ],
)
def test_dangerous_permissions_always_rejected(attr: str) -> None:
    perms = dataclasses.replace(BASE, **{attr: True})
    for policy in KeyPolicy:
        assert evaluate(perms, policy, require_ip_restrict=False), (attr, policy)


def test_trading_permission_rejected_under_read_only() -> None:
    perms = dataclasses.replace(BASE, enable_spot_and_margin_trading=True)
    assert any("read_only" in v for v in evaluate(perms, KeyPolicy.READ_ONLY, False))
    assert evaluate(perms, KeyPolicy.TRADE, False) == []


def test_trade_policy_requires_trading_permission() -> None:
    assert evaluate(BASE, KeyPolicy.TRADE, False)


def test_reading_required() -> None:
    perms = dataclasses.replace(BASE, enable_reading=False)
    assert evaluate(perms, KeyPolicy.READ_ONLY, False)


def test_ip_restriction_required_only_when_asked() -> None:
    perms = dataclasses.replace(BASE, ip_restrict=False)
    assert evaluate(perms, KeyPolicy.READ_ONLY, require_ip_restrict=False) == []
    assert any("IP" in v for v in evaluate(perms, KeyPolicy.READ_ONLY, True))
