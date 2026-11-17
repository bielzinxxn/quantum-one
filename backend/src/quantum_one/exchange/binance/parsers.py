"""JSON bruto da Binance (números como string) → modelos de domínio com Decimal."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from quantum_one.exchange.models import (
    AccountSnapshot,
    AccountTrade,
    Balance,
    CommissionRates,
    KeyPermissions,
    OpenOrder,
    RateLimit,
    SymbolCommission,
)
from quantum_one.marketdata.models import Candle

_INTERVAL_SECONDS = {"SECOND": 1, "MINUTE": 60, "HOUR": 3600, "DAY": 86400}
_KEY_FIELDS = {
    "ipRestrict": "ip_restrict",
    "enableReading": "enable_reading",
    "enableSpotAndMarginTrading": "enable_spot_and_margin_trading",
    "enableWithdrawals": "enable_withdrawals",
    "enableInternalTransfer": "enable_internal_transfer",
    "permitsUniversalTransfer": "permits_universal_transfer",
    "enableMargin": "enable_margin",
    "enableFutures": "enable_futures",
    "enableVanillaOptions": "enable_vanilla_options",
    "enablePortfolioMarginTrading": "enable_portfolio_margin_trading",
}


def ms_to_dt(ms: int | str) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC)


def parse_rate_limits(raw: list[dict[str, Any]]) -> list[RateLimit]:
    return [
        RateLimit(
            kind=r["rateLimitType"],
            interval_seconds=_INTERVAL_SECONDS[r["interval"]] * int(r["intervalNum"]),
            limit=int(r["limit"]),
        )
        for r in raw
        if r.get("interval") in _INTERVAL_SECONDS
    ]


def weight_limit_per_minute(limits: list[RateLimit]) -> int | None:
    for r in limits:
        if r.kind == "REQUEST_WEIGHT" and r.interval_seconds == 60:
            return r.limit
    return None


def parse_account(raw: dict[str, Any], now: datetime | None = None) -> AccountSnapshot:
    rates = raw.get("commissionRates", {})
    balances = tuple(
        Balance(b["asset"], Decimal(b["free"]), Decimal(b["locked"]))
        for b in raw.get("balances", [])
    )
    return AccountSnapshot(
        taken_at=now or datetime.now(tz=UTC),
        balances=tuple(b for b in balances if b.total > 0),
        can_trade=bool(raw.get("canTrade", False)),
        account_type=str(raw.get("accountType", "")),
        maker_commission=Decimal(rates.get("maker", "0")),
        taker_commission=Decimal(rates.get("taker", "0")),
    )


def parse_open_order(raw: dict[str, Any]) -> OpenOrder:
    return OpenOrder(
        symbol=raw["symbol"],
        order_id=int(raw["orderId"]),
        client_order_id=raw["clientOrderId"],
        side=raw["side"],
        type=raw["type"],
        status=raw["status"],
        price=Decimal(raw["price"]),
        orig_qty=Decimal(raw["origQty"]),
        executed_qty=Decimal(raw["executedQty"]),
        created_at=ms_to_dt(raw["time"]),
    )


def parse_trade(raw: dict[str, Any]) -> AccountTrade:
    return AccountTrade(
        symbol=raw["symbol"],
        trade_id=int(raw["id"]),
        order_id=int(raw["orderId"]),
        price=Decimal(raw["price"]),
        qty=Decimal(raw["qty"]),
        quote_qty=Decimal(raw["quoteQty"]),
        commission=Decimal(raw["commission"]),
        commission_asset=raw["commissionAsset"],
        is_buyer=bool(raw["isBuyer"]),
        is_maker=bool(raw["isMaker"]),
        executed_at=ms_to_dt(raw["time"]),
    )


def _rates(raw: dict[str, Any]) -> CommissionRates:
    return CommissionRates(
        maker=Decimal(raw.get("maker", "0")),
        taker=Decimal(raw.get("taker", "0")),
        buyer=Decimal(raw.get("buyer", "0")),
        seller=Decimal(raw.get("seller", "0")),
    )


def parse_commission(raw: dict[str, Any]) -> SymbolCommission:
    discount = raw.get("discount", {})
    return SymbolCommission(
        symbol=raw["symbol"],
        standard=_rates(raw.get("standardCommission", {})),
        special=_rates(raw.get("specialCommission", {})),
        tax=_rates(raw.get("taxCommission", {})),
        bnb_discount_enabled=bool(discount.get("enabledForAccount"))
        and bool(discount.get("enabledForSymbol")),
        bnb_discount_multiplier=Decimal(discount.get("discount", "1")),
    )


def parse_key_permissions(raw: dict[str, Any]) -> KeyPermissions:
    """Campo ausente = tratado como o valor MAIS PERIGOSO (fail-closed)."""
    values: dict[str, Any] = {}
    for api_name, attr in _KEY_FIELDS.items():
        if api_name in raw:
            values[attr] = bool(raw[api_name])
        else:
            # ausente: leitura/restrição de IP = False; permissões perigosas = True
            values[attr] = attr not in ("enable_reading", "ip_restrict")
    unknown = {k: v for k, v in raw.items() if k not in _KEY_FIELDS}
    return KeyPermissions(**values, raw_unknown=unknown)


def parse_rest_kline(symbol: str, row: list[Any]) -> Candle:
    """Linha de GET /api/v3/klines: [openTime, o, h, l, c, v, closeTime, quoteVol, trades, ...]."""
    return Candle(
        symbol=symbol,
        open_time_ms=int(row[0]),
        open=Decimal(row[1]),
        high=Decimal(row[2]),
        low=Decimal(row[3]),
        close=Decimal(row[4]),
        volume=Decimal(row[5]),
        close_time_ms=int(row[6]),
        quote_volume=Decimal(row[7]),
        trades=int(row[8]),
    )


def parse_quote_volumes(raw: list[dict[str, Any]]) -> dict[str, float]:
    """GET /api/v3/ticker/24hr (sem symbol) → {symbol: quoteVolume}."""
    return {r["symbol"]: float(r["quoteVolume"]) for r in raw if "quoteVolume" in r}
