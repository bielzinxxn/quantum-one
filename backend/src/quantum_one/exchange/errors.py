"""Classificação de erros da exchange em categorias acionáveis.

A classificação decide o comportamento: tentar de novo, esperar (rate limit),
bloquear (credencial/permissão/relógio) ou falhar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

import ccxt


class ErrorKind(StrEnum):
    RETRYABLE = "retryable"  # rede, timeout, exchange indisponível
    RATE_LIMITED = "rate_limited"  # 429
    IP_BANNED = "ip_banned"  # 418
    AUTH = "auth"  # chave inválida, IP não autorizado, sem permissão
    CLOCK = "clock"  # -1021: timestamp fora do recvWindow
    FATAL = "fatal"  # qualquer outra coisa: não insistir


@dataclass(frozen=True)
class ClassifiedError:
    kind: ErrorKind
    code: int | None
    message: str


_CODE = re.compile(r'"code"\s*:\s*(-?\d+)')
# o CCXT formata a mensagem como "binance 429 Too Many Requests {...}"
_HTTP_STATUS = re.compile(r"^\S+\s+(\d{3})(?:\s|$)")


def _binance_code(text: str) -> int | None:
    match = _CODE.search(text)
    return int(match.group(1)) if match else None


def _http_status(text: str) -> int | None:
    match = _HTTP_STATUS.match(text)
    return int(match.group(1)) if match else None


def classify(exc: BaseException) -> ClassifiedError:
    text = str(exc)
    code = _binance_code(text)
    status = _http_status(text)
    short = text[:300]
    if code == -1021 or isinstance(exc, ccxt.InvalidNonce):
        return ClassifiedError(ErrorKind.CLOCK, code, short)
    # Decide pelo status HTTP: o CCXT usa DDoSProtection tanto para 418 quanto para 429
    # (verificado no teste e2e contra o CCXT 4.5.92).
    if status == 418:
        return ClassifiedError(ErrorKind.IP_BANNED, code, short)
    if (
        status == 429
        or code == -1003
        or isinstance(exc, ccxt.DDoSProtection | ccxt.RateLimitExceeded)
    ):
        return ClassifiedError(ErrorKind.RATE_LIMITED, code, short)
    if isinstance(exc, ccxt.AuthenticationError | ccxt.PermissionDenied) or code in (-2014, -2015):
        return ClassifiedError(ErrorKind.AUTH, code, short)
    if isinstance(exc, ccxt.NetworkError | TimeoutError | ConnectionError):
        return ClassifiedError(ErrorKind.RETRYABLE, code, short)
    return ClassifiedError(ErrorKind.FATAL, code, short)
