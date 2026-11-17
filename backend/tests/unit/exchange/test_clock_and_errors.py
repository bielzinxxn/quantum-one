from __future__ import annotations

import ccxt
import pytest

from quantum_one.exchange.clock import measure_offset
from quantum_one.exchange.errors import ErrorKind, classify


async def test_offset_uses_midpoint_and_lowest_rtt_sample() -> None:
    times = iter([0.0, 100.0, 1000.0, 1010.0, 2000.0, 2300.0])  # RTTs: 100, 10, 300
    servers = iter([1050, 2505, 3150])

    async def server() -> int:
        return next(servers)

    reading = await measure_offset(server, local_ms=lambda: next(times), samples=3)
    assert reading.rtt_ms == 10
    assert reading.offset_ms == 2505 - 1005
    assert not reading.within(1000)
    assert reading.within(1500)


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (ccxt.RateLimitExceeded("binance 429"), ErrorKind.RATE_LIMITED),
        (ccxt.DDoSProtection("binance 418 I'm a teapot {}"), ErrorKind.IP_BANNED),
        (ccxt.DDoSProtection("binance 429 Too Many Requests {}"), ErrorKind.RATE_LIMITED),
        (ccxt.DDoSProtection("sem status"), ErrorKind.RATE_LIMITED),
        (
            ccxt.ExchangeError('binance {"code":-1003,"msg":"Too much weight"}'),
            ErrorKind.RATE_LIMITED,
        ),
        (ccxt.InvalidNonce("binance time"), ErrorKind.CLOCK),
        (
            ccxt.BadRequest('binance {"code":-1021,"msg":"Timestamp outside recvWindow"}'),
            ErrorKind.CLOCK,
        ),
        (
            ccxt.AuthenticationError('binance {"code":-2015,"msg":"Invalid API-key"}'),
            ErrorKind.AUTH,
        ),
        (ccxt.PermissionDenied("no perm"), ErrorKind.AUTH),
        (ccxt.RequestTimeout("timeout"), ErrorKind.RETRYABLE),
        (ccxt.ExchangeNotAvailable("maintenance"), ErrorKind.RETRYABLE),
        (TimeoutError(), ErrorKind.RETRYABLE),
        (ValueError("x"), ErrorKind.FATAL),
    ],
)
def test_classification(exc: BaseException, kind: ErrorKind) -> None:
    assert classify(exc).kind is kind


def test_code_extracted() -> None:
    err = classify(ccxt.AuthenticationError('binance {"code":-2015,"msg":"x"}'))
    assert err.code == -2015
