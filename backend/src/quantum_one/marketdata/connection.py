"""Cliente do stream combinado com reconexão (ADR-009 §3).

Emite `Connected`/`Disconnected` além das mensagens, para o consumidor disparar
preenchimento de lacunas e marcar dados como velhos.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections.abc import AsyncIterator, Callable

import aiohttp

from quantum_one.core.logging import get_logger
from quantum_one.marketdata.messages import parse_frame
from quantum_one.marketdata.models import Connected, Disconnected, ServerShutdown, StreamEvent


def backoff_s(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """Exponencial com jitter: 1, 2, 4 ... até 60 s (+ até 1 s aleatório)."""
    return float(min(cap, base * (2 ** max(0, attempt)))) + random.random()  # noqa: S311


CLOSE_TIMEOUT_S = 3.0


async def close_ws(ws: aiohttp.ClientWebSocketResponse) -> None:
    """Fecha com prazo total. O `ws_close` do aiohttp vale POR LEITURA: se o servidor
    continua enviando dados, `close()` não termina. Cancelado, o aiohttp aborta a conexão."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(ws.close(), timeout=CLOSE_TIMEOUT_S)


class MarketStream:
    def __init__(
        self,
        url: Callable[[], str],
        silence_timeout_s: float,
        rotate_after_s: float,
        backoff: Callable[[int], float] = backoff_s,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._silence = silence_timeout_s
        self._rotate = rotate_after_s
        self._backoff = backoff
        self._clock = clock
        self._reconnect = asyncio.Event()
        self.connected = False
        self.reconnects = 0
        self.unknown_messages = 0

    def request_reconnect(self) -> None:
        """Pede nova conexão (p.ex. universo mudou)."""
        self._reconnect.set()

    async def events(self, stop: asyncio.Event) -> AsyncIterator[StreamEvent]:
        log = get_logger()
        attempt = 0
        # timeouts explícitos: conexão travada ou fechamento sem resposta não podem
        # segurar o desligamento (o Docker mata o processo após stop_grace_period)
        session_timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, connect=15)
        ws_timeout = aiohttp.ClientWSTimeout(ws_receive=None, ws_close=2.0)
        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            while not stop.is_set():
                url = self._url()
                reason = "closed"
                self._reconnect.clear()
                ws: aiohttp.ClientWebSocketResponse | None = None
                try:
                    ws = await session.ws_connect(
                        url, autoping=True, heartbeat=None, timeout=ws_timeout
                    )
                    self.connected, attempt, opened = True, 0, self._clock()
                    yield Connected(url.split("?")[0])
                    while not stop.is_set():
                        if self._reconnect.is_set():
                            reason = "reconnect_requested"
                            break
                        if self._clock() - opened > self._rotate:
                            reason = "rotation"  # antes do limite de 24 h
                            break
                        msg = await asyncio.wait_for(ws.receive(), timeout=self._silence)
                        if msg.type is aiohttp.WSMsgType.TEXT:
                            parsed = parse_frame(msg.data)
                            if parsed is None:
                                self.unknown_messages += 1
                                continue
                            yield parsed
                            if isinstance(parsed, ServerShutdown):
                                reason = "server_shutdown"
                                break
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            reason = f"ws_{msg.type.name.lower()}"
                            break
                except TimeoutError:
                    reason = "silence_timeout"
                except (aiohttp.ClientError, OSError) as exc:
                    reason = f"connect_error:{type(exc).__name__}"
                finally:
                    if ws is not None:
                        await close_ws(ws)
                if stop.is_set():
                    reason = "stopped"
                was_connected, self.connected = self.connected, False
                yield Disconnected(reason)
                if stop.is_set():
                    break
                if was_connected:
                    self.reconnects += 1
                planned = reason in ("rotation", "reconnect_requested", "server_shutdown")
                wait = 0.0 if planned and was_connected else self._backoff(attempt)
                attempt += 0 if planned else 1
                log.warning("market_stream_disconnected", reason=reason, retry_in_s=round(wait, 1))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=wait)
