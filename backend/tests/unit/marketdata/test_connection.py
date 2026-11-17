"""MarketStream contra o servidor WebSocket falso: reconexão, silêncio, shutdown, rotação."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from aiohttp import web

from quantum_one.marketdata.connection import MarketStream, backoff_s
from quantum_one.marketdata.models import BookTop, Connected, Disconnected, KlineUpdate, StreamEvent
from tests.fakes.fake_ws import FakeStreamServer, book_frame, kline_frame, shutdown_frame, start_ws

T0 = 1_700_000_040_000


async def collect(
    stream: MarketStream, until: Callable[[list[StreamEvent]], bool], max_s: float = 5
) -> list[StreamEvent]:
    stop = asyncio.Event()
    events: list[StreamEvent] = []

    async def run() -> None:
        async for ev in stream.events(stop):
            events.append(ev)
            if until(events):
                stop.set()

    await asyncio.wait_for(run(), timeout=max_s)
    return events


def kinds(events: list[StreamEvent]) -> list[str]:
    return [type(e).__name__ for e in events]


async def _serve(script: Any) -> tuple[Any, str, FakeStreamServer]:
    fake = FakeStreamServer(script)
    server, base = await start_ws(fake)
    return server, f"{base}/stream?streams=btcusdt@kline_1m/btcusdt@bookTicker", fake


async def test_receives_messages_and_reconnects_after_server_close() -> None:
    async def script(ws: web.WebSocketResponse, i: int) -> None:
        await ws.send_str(kline_frame("BTCUSDT", T0, "100", True))
        await ws.send_str(book_frame("BTCUSDT", "99", "101"))
        await ws.send_str('{"result": null, "id": 1}')  # desconhecida → contada

    server, url, fake = await _serve(script)
    stream = MarketStream(
        lambda: url, silence_timeout_s=2, rotate_after_s=3600, backoff=lambda attempt: 0.01
    )
    try:
        events = await collect(stream, lambda ev: kinds(ev).count("Connected") == 2)
    finally:
        await server.close()
    assert kinds(events)[:4] == ["Connected", "KlineUpdate", "BookTop", "Disconnected"]
    assert isinstance(events[1], KlineUpdate) and isinstance(events[2], BookTop)
    assert stream.reconnects == 1 and stream.unknown_messages >= 1
    assert fake.connections[0]["streams"] == ["btcusdt@kline_1m", "btcusdt@bookTicker"]


async def test_silence_triggers_reconnect() -> None:
    async def script(ws: web.WebSocketResponse, i: int) -> None:
        await asyncio.sleep(10)  # mudo

    server, url, _ = await _serve(script)
    stream = MarketStream(
        lambda: url, silence_timeout_s=0.3, rotate_after_s=3600, backoff=lambda attempt: 0.01
    )
    try:
        events = await collect(stream, lambda ev: kinds(ev).count("Disconnected") == 1)
    finally:
        await server.close()
    assert isinstance(events[-1], Disconnected) and events[-1].reason == "silence_timeout"


async def test_server_shutdown_reconnects_immediately_without_backoff() -> None:
    backoffs: list[int] = []

    async def script(ws: web.WebSocketResponse, i: int) -> None:
        await ws.send_str(shutdown_frame(T0))
        await asyncio.sleep(1)

    server, url, _ = await _serve(script)
    stream = MarketStream(lambda: url, 2, 3600, backoff=lambda a: backoffs.append(a) or 0.01)
    try:
        events = await collect(stream, lambda ev: kinds(ev).count("Connected") == 2)
    finally:
        await server.close()
    reasons = [e.reason for e in events if isinstance(e, Disconnected)]
    assert reasons[0] == "server_shutdown"
    assert backoffs == []  # reconexão planejada: sem espera


async def test_request_reconnect_and_rotation() -> None:
    async def script(ws: web.WebSocketResponse, i: int) -> None:
        for _ in range(50):
            await ws.send_str(book_frame("BTCUSDT", "99", "101"))
            await asyncio.sleep(0.02)

    server, url, _ = await _serve(script)
    stream = MarketStream(lambda: url, 2, rotate_after_s=0.1, backoff=lambda a: 0.01)
    try:
        events = await collect(stream, lambda ev: kinds(ev).count("Connected") == 2)
        reasons = [e.reason for e in events if isinstance(e, Disconnected)]
        assert reasons == ["rotation", "stopped"]

        stream2 = MarketStream(lambda: url, 2, 3600, backoff=lambda a: 0.01)

        def until(ev: list[StreamEvent]) -> bool:
            if kinds(ev).count("BookTop") == 2:
                stream2.request_reconnect()
            return kinds(ev).count("Connected") == 2

        events = await collect(stream2, until)
        reasons = [e.reason for e in events if isinstance(e, Disconnected)]
        assert reasons == ["reconnect_requested", "stopped"]
    finally:
        await server.close()


async def test_connect_error_uses_backoff() -> None:
    attempts: list[int] = []
    stream = MarketStream(
        lambda: "ws://127.0.0.1:1/stream", 1, 3600, backoff=lambda a: attempts.append(a) or 0.01
    )
    events = await collect(stream, lambda ev: len(ev) >= 3)
    assert all(isinstance(e, Disconnected) for e in events)
    assert events[0].reason.startswith("connect_error")  # type: ignore[union-attr]
    assert attempts[:2] == [0, 1]  # backoff cresce a cada falha
    assert not any(isinstance(e, Connected) for e in events)


def test_backoff_growth_and_cap() -> None:
    assert 1 <= backoff_s(0) < 2
    assert 8 <= backoff_s(3) < 9
    assert 60 <= backoff_s(20) < 61


async def test_stop_is_bounded_even_if_server_keeps_streaming() -> None:
    """Regressão: o close() do aiohttp não termina se o servidor nunca responde ao CLOSE."""
    import time

    async def script(ws: web.WebSocketResponse, i: int) -> None:
        for _ in range(400):  # transmite ~20 s sem ler o frame de fechamento
            await ws.send_str(book_frame("BTCUSDT", "1", "2"))
            await asyncio.sleep(0.05)

    server, url, _ = await _serve(script)
    stream = MarketStream(lambda: url, 5, 3600, backoff=lambda a: 0.01)
    stop = asyncio.Event()
    stopped_at: list[float] = []

    async def run() -> None:
        async for ev in stream.events(stop):
            if isinstance(ev, BookTop) and not stop.is_set():
                stop.set()
                stopped_at.append(time.monotonic())

    try:
        await asyncio.wait_for(run(), timeout=10)
        assert time.monotonic() - stopped_at[0] < 4.5  # CLOSE_TIMEOUT_S = 3
    finally:
        await server.close()
