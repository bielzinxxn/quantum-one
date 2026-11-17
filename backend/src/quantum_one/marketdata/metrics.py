"""Métricas do scanner — funções puras e determinísticas.

Profundidade e slippage usam só os níveis visíveis (depth20): são LIMITES INFERIORES
e retornam `truncated=True` quando o último nível visível ainda está dentro da faixa.
"""

from __future__ import annotations

import itertools
import math
import statistics
from collections.abc import Sequence

MINUTES_PER_YEAR = 525_600
Levels = Sequence[tuple[float, float]]


def mid(bid: float, ask: float) -> float | None:
    return (bid + ask) / 2 if bid > 0 and ask > 0 and ask >= bid else None


def spread_bps(bid: float, ask: float) -> float | None:
    m = mid(bid, ask)
    return (ask - bid) / m * 10_000 if m else None


def depth_within(levels: Levels, mid_price: float, pct: float, side: str) -> tuple[float, bool]:
    """Notional (em quote) dentro de ±pct% do mid. Retorna (notional, truncado)."""
    if side not in ("bid", "ask"):
        raise ValueError(side)
    limit = mid_price * (1 - pct / 100) if side == "bid" else mid_price * (1 + pct / 100)
    total = 0.0
    for price, qty in levels:
        inside = price >= limit if side == "bid" else price <= limit
        if not inside:
            return total, False
        total += price * qty
    return total, bool(levels)  # todos os níveis visíveis estavam dentro da faixa


def slippage_bps(levels: Levels, mid_price: float, quote_amount: float, side: str) -> float | None:
    """Custo de executar `quote_amount` a mercado varrendo o livro, em bps contra o mid.

    side="buy" consome asks; side="sell" consome bids. None = livro visível insuficiente.
    """
    if quote_amount <= 0 or mid_price <= 0:
        return None
    remaining, cost_qty = quote_amount, 0.0
    for price, qty in levels:
        notional = price * qty
        take = min(notional, remaining)
        cost_qty += take / price
        remaining -= take
        if remaining <= 1e-9:
            vwap = quote_amount / cost_qty
            diff = vwap - mid_price if side == "buy" else mid_price - vwap
            return diff / mid_price * 10_000
    return None


def log_returns(closes: Sequence[float]) -> list[float]:
    return [math.log(b / a) for a, b in itertools.pairwise(closes) if a > 0 and b > 0]


def simple_return(closes: Sequence[float], lookback: int) -> float | None:
    if len(closes) <= lookback or closes[-1 - lookback] <= 0:
        return None
    return closes[-1] / closes[-1 - lookback] - 1


def return_zscore(closes: Sequence[float], window: int = 240, min_obs: int = 30) -> float | None:
    """Último retorno de 1m em desvios-padrão dos `window` retornos ANTERIORES."""
    rets = log_returns(closes)
    if len(rets) < min_obs + 1:
        return None
    history = rets[-1 - window : -1]
    sd = statistics.pstdev(history)
    return rets[-1] / sd if sd > 0 else None


def relative_volume(volumes: Sequence[float], window: int = 60, min_obs: int = 20) -> float | None:
    """Volume do último minuto / mediana dos `window` minutos anteriores."""
    if len(volumes) < min_obs + 1:
        return None
    med = statistics.median(volumes[-1 - window : -1])
    return volumes[-1] / med if med > 0 else None


def realized_vol(closes: Sequence[float], window: int, min_obs: int = 30) -> float | None:
    """Desvio-padrão dos log-retornos de 1m, anualizado (√525600)."""
    rets = log_returns(closes)[-window:]
    if len(rets) < min_obs:
        return None
    return statistics.stdev(rets) * math.sqrt(MINUTES_PER_YEAR)
