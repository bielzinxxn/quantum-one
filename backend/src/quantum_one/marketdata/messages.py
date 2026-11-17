"""Parser dos frames do stream COMBINADO da Binance (web-socket-streams.md).

Formato: {"stream": "<nome>", "data": <payload>}. O payload de depth<N> não traz símbolo:
o símbolo vem do nome do stream. Mensagem desconhecida → None (contada pelo chamador).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from quantum_one.marketdata.models import BookTop, Candle, Depth, KlineUpdate, ServerShutdown

ParsedMessage = KlineUpdate | BookTop | Depth | ServerShutdown


def parse_candle(symbol: str, k: dict[str, Any]) -> Candle:
    return Candle(
        symbol=symbol,
        open_time_ms=int(k["t"]),
        close_time_ms=int(k["T"]),
        open=Decimal(k["o"]),
        high=Decimal(k["h"]),
        low=Decimal(k["l"]),
        close=Decimal(k["c"]),
        volume=Decimal(k["v"]),
        quote_volume=Decimal(k["q"]),
        trades=int(k["n"]),
        timeframe=str(k["i"]),
    )


def _levels(raw: list[list[str]]) -> tuple[tuple[float, float], ...]:
    return tuple((float(p), float(q)) for p, q in raw)


def parse_frame(text: str) -> ParsedMessage | None:
    try:
        frame = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(frame, dict) or "stream" not in frame or "data" not in frame:
        return None  # p.ex. resposta {"result": null, "id": 1}
    stream: str = frame["stream"]
    data: dict[str, Any] = frame["data"]
    try:
        if stream == "!serverShutdown" or data.get("e") == "serverShutdown":
            t = data.get("T")
            return ServerShutdown(int(t) if t is not None else None)
        symbol_lower, _, kind = stream.partition("@")
        symbol = symbol_lower.upper()
        if kind.startswith("kline_"):
            k = data["k"]
            return KlineUpdate(parse_candle(str(k["s"]), k), closed=bool(k["x"]))
        if kind == "bookTicker":
            return BookTop(
                str(data["s"]),
                float(data["b"]),
                float(data["B"]),
                float(data["a"]),
                float(data["A"]),
            )
        if kind.startswith("depth"):
            return Depth(symbol, _levels(data["bids"]), _levels(data["asks"]))
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    return None
