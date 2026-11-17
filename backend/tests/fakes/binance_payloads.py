"""Payloads no formato da documentação oficial (binance-spot-api-docs, CHANGELOG 2026-11-11).

Estrutura e nomes de campos copiados dos exemplos de rest-api.md / filters.md e do modelo
GetApiKeyPermissionResponse do SDK oficial. Valores numéricos são ilustrativos.
"""

from __future__ import annotations

from typing import Any

BTCUSDT: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "status": "TRADING",
    "baseAsset": "BTC",
    "baseAssetPrecision": 8,
    "quoteAsset": "USDT",
    "quoteAssetPrecision": 8,
    "orderTypes": ["LIMIT", "LIMIT_MAKER", "MARKET", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"],
    "ocoAllowed": True,
    "isSpotTradingAllowed": True,
    "filters": [
        {
            "filterType": "PRICE_FILTER",
            "minPrice": "0.01000000",
            "maxPrice": "1000000.00000000",
            "tickSize": "0.01000000",
        },
        {
            "filterType": "LOT_SIZE",
            "minQty": "0.00001000",
            "maxQty": "9000.00000000",
            "stepSize": "0.00001000",
        },
        {
            "filterType": "NOTIONAL",
            "minNotional": "5.00000000",
            "applyMinToMarket": True,
            "maxNotional": "9000000.00000000",
            "applyMaxToMarket": False,
            "avgPriceMins": 5,
        },
    ],
    "permissionSets": [["SPOT", "MARGIN"]],
}

ETHBTC_LEGACY: dict[str, Any] = {
    "symbol": "ETHBTC",
    "status": "BREAK",
    "baseAsset": "ETH",
    "quoteAsset": "BTC",
    "orderTypes": ["LIMIT", "MARKET"],
    "isSpotTradingAllowed": True,
    "filters": [
        {"filterType": "PRICE_FILTER", "minPrice": "0", "maxPrice": "0", "tickSize": "0.000001"},
        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100000", "stepSize": "0.001"},
        {
            "filterType": "MIN_NOTIONAL",
            "minNotional": "0.0001",
            "applyToMarket": True,
            "avgPriceMins": 5,
        },
    ],
}

EXCHANGE_INFO: dict[str, Any] = {
    "timezone": "UTC",
    "serverTime": 1565246363776,
    "rateLimits": [
        {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 6000},
        {"rateLimitType": "ORDERS", "interval": "SECOND", "intervalNum": 10, "limit": 50},
        {"rateLimitType": "ORDERS", "interval": "DAY", "intervalNum": 1, "limit": 160000},
        {"rateLimitType": "RAW_REQUESTS", "interval": "MINUTE", "intervalNum": 5, "limit": 61000},
    ],
    "exchangeFilters": [],
    "symbols": [BTCUSDT, ETHBTC_LEGACY],
}

ACCOUNT: dict[str, Any] = {
    "makerCommission": 10,
    "takerCommission": 10,
    "commissionRates": {
        "maker": "0.00100000",
        "taker": "0.00100000",
        "buyer": "0.00000000",
        "seller": "0.00000000",
    },
    "canTrade": True,
    "canWithdraw": True,
    "canDeposit": True,
    "accountType": "SPOT",
    "balances": [
        {"asset": "BTC", "free": "0.01234567", "locked": "0.00000000"},
        {"asset": "USDT", "free": "1500.12345678", "locked": "250.00000000"},
        {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"},
    ],
    "permissions": ["SPOT"],
    "uid": 354937868,
}

OPEN_ORDERS: list[dict[str, Any]] = [
    {
        "symbol": "BTCUSDT",
        "orderId": 1,
        "orderListId": -1,
        "clientOrderId": "myOrder1",
        "price": "60000.01",
        "origQty": "0.001",
        "executedQty": "0.0",
        "cummulativeQuoteQty": "0.0",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "BUY",
        "time": 1499827319559,
        "updateTime": 1499827319559,
        "isWorking": True,
    },
]

MY_TRADES: list[dict[str, Any]] = [
    {
        "symbol": "BTCUSDT",
        "id": 28457,
        "orderId": 100234,
        "orderListId": -1,
        "price": "60000.10000000",
        "qty": "0.00100000",
        "quoteQty": "60.00010000",
        "commission": "0.00007500",
        "commissionAsset": "BNB",
        "time": 1499865549590,
        "isBuyer": True,
        "isMaker": False,
        "isBestMatch": True,
    },
]

COMMISSION: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "standardCommission": {
        "maker": "0.00100000",
        "taker": "0.00100000",
        "buyer": "0.00000000",
        "seller": "0.00000000",
    },
    "specialCommission": {
        "maker": "0.00000000",
        "taker": "0.00000000",
        "buyer": "0.00000000",
        "seller": "0.00000000",
    },
    "taxCommission": {
        "maker": "0.00000000",
        "taker": "0.00000000",
        "buyer": "0.00000000",
        "seller": "0.00000000",
    },
    "discount": {
        "enabledForAccount": True,
        "enabledForSymbol": True,
        "discountAsset": "BNB",
        "discount": "0.75000000",
    },
}

KEY_READ_ONLY: dict[str, Any] = {
    "ipRestrict": True,
    "createTime": 1698645219000,
    "enableReading": True,
    "enableWithdrawals": False,
    "enableInternalTransfer": False,
    "enableMargin": False,
    "enableFutures": False,
    "permitsUniversalTransfer": False,
    "enableVanillaOptions": False,
    "enableFixApiTrade": False,
    "enableFixReadOnly": False,
    "enableSpotAndMarginTrading": False,
    "enablePortfolioMarginTrading": False,
}
