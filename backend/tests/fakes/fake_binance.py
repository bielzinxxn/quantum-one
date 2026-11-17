"""Servidor Binance falso (aiohttp) para testar o CCXT real de ponta a ponta, sem rede.

- Verifica assinatura HMAC-SHA256 ou Ed25519 sobre a query string (regra da doc oficial:
  payload = query string sem o parâmetro `signature`).
- Exige `X-MBX-APIKEY`, `timestamp` e `recvWindow` em endpoints assinados.
- Devolve `X-MBX-USED-WEIGHT-1M` acumulado.
- Modos de falha injetáveis por rota: 429, 418, -1021, -2015.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from aiohttp import web
from aiohttp.test_utils import TestServer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tests.fakes import binance_payloads as P

SIGNED = {
    "/api/v3/account",
    "/api/v3/openOrders",
    "/api/v3/myTrades",
    "/api/v3/account/commission",
    "/sapi/v1/account/apiRestrictions",
}
WEIGHTS = {
    "/api/v3/time": 1,
    "/api/v3/exchangeInfo": 20,
    "/api/v3/account": 20,
    "/api/v3/openOrders": 80,
    "/api/v3/myTrades": 20,
    "/api/v3/account/commission": 20,
    "/sapi/v1/account/apiRestrictions": 1,
}


@dataclass
class FakeBinance:
    api_key: str = "test-api-key"
    hmac_secret: str | None = None
    ed25519_public: Ed25519PublicKey | None = None
    server_time_offset_ms: int = 0
    key_permissions: dict[str, Any] = field(default_factory=lambda: dict(P.KEY_READ_ONLY))
    failures: dict[str, tuple[int, dict[str, Any], dict[str, str]]] = field(default_factory=dict)
    used_weight: int = 0
    requests: list[dict[str, str]] = field(default_factory=list)
    quote_volumes: dict[str, str] = field(
        default_factory=lambda: {"BTCUSDT": "900000000.0", "ETHBTC": "1000.0"}
    )
    now_ms: int | None = None  # relógio do servidor falso para klines (None = tempo real)

    def klines(self, symbol: str, start: int, end: int | None, limit: int) -> list[list[Any]]:
        """Velas sintéticas determinísticas; inclui a vela EM ANDAMENTO, como a Binance."""
        now = self.now_ms if self.now_ms is not None else int(time.time() * 1000)
        step = 60_000
        t = start - start % step if start % step == 0 else start - start % step + step
        stop = min(end if end is not None else now, now)
        rows: list[list[Any]] = []
        while t <= stop and len(rows) < limit:
            price = f"{60000 + (t // step) % 100}.00"
            rows.append(
                [
                    t,
                    price,
                    price,
                    price,
                    price,
                    "1.5",
                    t + step - 1,
                    "90000.0",
                    42,
                    "0.7",
                    "42000.0",
                    "0",
                ]
            )
            t += step
        return rows

    def fail(
        self, path: str, status: int, code: int, msg: str, headers: dict[str, str] | None = None
    ) -> None:
        self.failures[path] = (status, {"code": code, "msg": msg}, headers or {})

    def _verify(self, request: web.Request) -> web.Response | None:
        raw = request.query_string
        if "&signature=" not in raw:
            return web.json_response({"code": -1102, "msg": "signature missing"}, status=400)
        payload, signature = raw.rsplit("&signature=", 1)
        signature = unquote(signature)
        if request.headers.get("X-MBX-APIKEY") != self.api_key:
            return web.json_response({"code": -2015, "msg": "Invalid API-key"}, status=401)
        params = request.query
        if "timestamp" not in params or "recvWindow" not in params:
            return web.json_response({"code": -1102, "msg": "timestamp/recvWindow"}, status=400)
        if self.hmac_secret is not None:
            expected = hmac.new(
                self.hmac_secret.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()
            valid = hmac.compare_digest(expected, signature.lower())
        else:
            assert self.ed25519_public is not None
            try:
                self.ed25519_public.verify(base64.b64decode(signature), payload.encode())
                valid = True
            except Exception:
                valid = False
        if not valid:
            return web.json_response({"code": -1022, "msg": "Signature invalid"}, status=400)
        return None

    async def handle(self, request: web.Request) -> web.Response:
        path = request.path
        self.requests.append({"path": path, "query": request.query_string})
        if path in self.failures:
            status, body, headers = self.failures[path]
            return web.json_response(body, status=status, headers=headers)
        if path in SIGNED and (err := self._verify(request)) is not None:
            return err
        self.used_weight += WEIGHTS.get(path, 1)
        if path == "/api/v3/klines":
            q = request.query
            end = int(q["endTime"]) if "endTime" in q else None
            rows = self.klines(q["symbol"], int(q["startTime"]), end, int(q.get("limit", 500)))
            return web.json_response(rows, headers={"X-MBX-USED-WEIGHT-1M": str(self.used_weight)})
        if path == "/api/v3/ticker/24hr":
            tickers = [
                {"symbol": s, "quoteVolume": v, "lastPrice": "1"}
                for s, v in self.quote_volumes.items()
            ]
            return web.json_response(tickers)
        body: Any = {
            "/api/v3/time": {"serverTime": int(time.time() * 1000) + self.server_time_offset_ms},
            "/api/v3/exchangeInfo": P.EXCHANGE_INFO,
            "/api/v3/account": P.ACCOUNT,
            "/api/v3/openOrders": P.OPEN_ORDERS,
            "/api/v3/myTrades": P.MY_TRADES,
            "/api/v3/account/commission": P.COMMISSION,
            "/sapi/v1/account/apiRestrictions": self.key_permissions,
        }.get(path)
        if body is None:
            return web.json_response({"code": -1000, "msg": "unknown route"}, status=404)
        return web.json_response(body, headers={"X-MBX-USED-WEIGHT-1M": str(self.used_weight)})

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_route("GET", "/{tail:.*}", self.handle)
        return app


async def start(fake: FakeBinance) -> TestServer:
    server = TestServer(fake.app())
    await server.start_server()
    return server


def point_exchange_to(exchange: Any, server: TestServer) -> None:
    base = str(server.make_url("")).rstrip("/")
    exchange.urls["api"]["public"] = f"{base}/api/v3"
    exchange.urls["api"]["private"] = f"{base}/api/v3"
    exchange.urls["api"]["sapi"] = f"{base}/sapi/v1"
