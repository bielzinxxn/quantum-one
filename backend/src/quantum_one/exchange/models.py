"""Modelos de domínio da exchange. Todo valor monetário é `Decimal` (nunca float)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Instrument:
    symbol: str
    base: str
    quote: str
    status: str
    tick_size: Decimal
    min_price: Decimal
    max_price: Decimal
    step_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal
    max_notional: Decimal | None
    order_types: tuple[str, ...]
    spot_allowed: bool
    oco_allowed: bool

    @property
    def tradable(self) -> bool:
        return self.status == "TRADING" and self.spot_allowed


@dataclass(frozen=True)
class Balance:
    asset: str
    free: Decimal
    locked: Decimal

    @property
    def total(self) -> Decimal:
        return self.free + self.locked


@dataclass(frozen=True)
class AccountSnapshot:
    taken_at: datetime
    balances: tuple[Balance, ...]
    can_trade: bool
    account_type: str
    maker_commission: Decimal
    taker_commission: Decimal


@dataclass(frozen=True)
class OpenOrder:
    symbol: str
    order_id: int
    client_order_id: str
    side: str
    type: str
    status: str
    price: Decimal
    orig_qty: Decimal
    executed_qty: Decimal
    created_at: datetime


@dataclass(frozen=True)
class AccountTrade:
    """Execução (fill) confirmada pela exchange."""

    symbol: str
    trade_id: int
    order_id: int
    price: Decimal
    qty: Decimal
    quote_qty: Decimal
    commission: Decimal
    commission_asset: str
    is_buyer: bool
    is_maker: bool
    executed_at: datetime


@dataclass(frozen=True)
class CommissionRates:
    maker: Decimal
    taker: Decimal
    buyer: Decimal
    seller: Decimal


@dataclass(frozen=True)
class SymbolCommission:
    symbol: str
    standard: CommissionRates
    special: CommissionRates
    tax: CommissionRates
    bnb_discount_enabled: bool
    bnb_discount_multiplier: Decimal

    def effective(self, *, maker: bool) -> Decimal:
        """Taxa total (sem desconto BNB) somando standard + special + tax."""
        rates = (self.standard, self.special, self.tax)
        return sum((r.maker if maker else r.taker for r in rates), start=Decimal(0))


@dataclass(frozen=True)
class KeyPermissions:
    ip_restrict: bool
    enable_reading: bool
    enable_spot_and_margin_trading: bool
    enable_withdrawals: bool
    enable_internal_transfer: bool
    permits_universal_transfer: bool
    enable_margin: bool
    enable_futures: bool
    enable_vanilla_options: bool
    enable_portfolio_margin_trading: bool
    raw_unknown: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RateLimit:
    kind: str  # REQUEST_WEIGHT | ORDERS | RAW_REQUESTS
    interval_seconds: int
    limit: int
