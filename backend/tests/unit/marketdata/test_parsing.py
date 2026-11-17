from __future__ import annotations

import json
import uuid
from decimal import Decimal as D

from quantum_one.core.ids import uuid7
from quantum_one.marketdata.messages import parse_frame
from quantum_one.marketdata.models import BookTop, Depth, KlineUpdate, ServerShutdown
from quantum_one.marketdata.streams import combined_url, stream_names
from tests.fakes.fake_ws import book_frame, depth_frame, kline_frame, shutdown_frame


def test_uuid7_version_variant_and_ordering() -> None:
    a, b = uuid7(1_700_000_000_000), uuid7(1_700_000_000_001)
    assert a.version == 7 and a.variant == uuid.RFC_4122
    assert a < b
    assert a.int >> 80 == 1_700_000_000_000
    assert len({uuid7() for _ in range(1000)}) == 1000


def test_kline_closed_and_open() -> None:
    closed = parse_frame(kline_frame("BTCUSDT", 1_700_000_040_000, "60000.10", True, "123.45"))
    assert isinstance(closed, KlineUpdate) and closed.closed
    c = closed.candle
    assert (c.symbol, c.open_time_ms, c.close_time_ms) == (
        "BTCUSDT",
        1_700_000_040_000,
        1_700_000_099_999,
    )
    assert c.close == D("60000.10") and c.quote_volume == D("123.45") and c.trades == 10
    open_ = parse_frame(kline_frame("BTCUSDT", 1_700_000_040_000, "1", False))
    assert isinstance(open_, KlineUpdate) and not open_.closed


def test_book_ticker() -> None:
    b = parse_frame(book_frame("ETHUSDT", "3000.1", "3000.2", "7"))
    assert b == BookTop("ETHUSDT", 3000.1, 7.0, 3000.2, 7.0)


def test_depth_symbol_comes_from_stream_name() -> None:
    d = parse_frame(depth_frame("SOLUSDT", [["100", "1"], ["99", "2"]], [["101", "3"]]))
    assert isinstance(d, Depth)
    assert d.symbol == "SOLUSDT"
    assert d.bids == ((100.0, 1.0), (99.0, 2.0)) and d.asks == ((101.0, 3.0),)


def test_server_shutdown() -> None:
    assert parse_frame(shutdown_frame(1_770_124_000_000)) == ServerShutdown(1_770_124_000_000)


def test_unknown_or_malformed_messages_are_none() -> None:
    assert parse_frame('{"result": null, "id": 1}') is None
    assert parse_frame("não é json") is None
    assert parse_frame(json.dumps({"stream": "btcusdt@aggTrade", "data": {}})) is None
    broken = json.dumps({"stream": "btcusdt@kline_1m", "data": {"k": {"t": 1}}})
    assert parse_frame(broken) is None
    bad_number = json.dumps(
        {
            "stream": "btcusdt@bookTicker",
            "data": {"s": "BTCUSDT", "b": "x", "B": "1", "a": "1", "A": "1"},
        }
    )
    assert parse_frame(bad_number) is None


def test_stream_names_and_url() -> None:
    assert stream_names(["BTCUSDT"]) == [
        "btcusdt@kline_1m",
        "btcusdt@bookTicker",
        "btcusdt@depth20",
    ]
    url = combined_url("wss://stream.binance.com:9443", ["BTCUSDT", "ETHUSDT"])
    assert url.startswith("wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/")
    assert url.count("@") == 6


def test_url_limits() -> None:
    import pytest

    with pytest.raises(ValueError, match="vazio"):
        combined_url("wss://x", [])
    with pytest.raises(ValueError, match="limite"):
        combined_url("wss://x", [f"S{i}USDT" for i in range(400)])
