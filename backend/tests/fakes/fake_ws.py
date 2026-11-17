"""Servidor WebSocket falso no formato do stream combinado da Binance."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestServer

Script = Callable[[web.WebSocketResponse, int], Awaitable[None]]


def kline_frame(symbol: str, open_ms: int, close: str, closed: bool, qv: str = "1000") -> str:
    data = {
        "e": "kline",
        "E": open_ms + 1000,
        "s": symbol,
        "k": {
            "t": open_ms,
            "T": open_ms + 59_999,
            "s": symbol,
            "i": "1m",
            "f": 1,
            "L": 2,
            "o": close,
            "c": close,
            "h": close,
            "l": close,
            "v": "1",
            "n": 10,
            "x": closed,
            "q": qv,
            "V": "0.5",
            "Q": "500",
            "B": "0",
        },
    }
    return json.dumps({"stream": f"{symbol.lower()}@kline_1m", "data": data})


def book_frame(symbol: str, bid: str, ask: str, qty: str = "5") -> str:
    data = {"u": 1, "s": symbol, "b": bid, "B": qty, "a": ask, "A": qty}
    return json.dumps({"stream": f"{symbol.lower()}@bookTicker", "data": data})


def depth_frame(symbol: str, bids: list[list[str]], asks: list[list[str]]) -> str:
    data = {"lastUpdateId": 1, "bids": bids, "asks": asks}
    return json.dumps({"stream": f"{symbol.lower()}@depth20", "data": data})


def shutdown_frame(t_ms: int) -> str:
    return json.dumps(
        {"stream": "!serverShutdown", "data": {"e": "serverShutdown", "E": t_ms - 1000, "T": t_ms}}
    )


@dataclass
class FakeStreamServer:
    script: Script
    connections: list[dict[str, Any]] = field(default_factory=list)

    async def handle(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(autoping=True)
        await ws.prepare(request)
        index = len(self.connections)
        self.connections.append({"streams": request.query.get("streams", "").split("/")})
        await self.script(ws, index)
        if not ws.closed:
            await ws.close()
        return ws

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/stream", self.handle)
        return app


async def start_ws(fake: FakeStreamServer) -> tuple[TestServer, str]:
    server = TestServer(fake.app())
    await server.start_server()
    base = str(server.make_url("")).rstrip("/").replace("http://", "ws://")
    return server, base
