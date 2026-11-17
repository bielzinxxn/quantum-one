"""Métricas contra valores calculados à mão."""

from __future__ import annotations

import math

import pytest

from quantum_one.marketdata import metrics as m


def test_spread_and_mid() -> None:
    assert m.mid(99.0, 101.0) == 100.0
    assert m.spread_bps(99.0, 101.0) == pytest.approx(200.0)
    assert m.spread_bps(0.0, 101.0) is None
    assert m.spread_bps(101.0, 99.0) is None  # livro cruzado = dado inválido


BIDS = [(99.9, 1.0), (99.5, 2.0), (98.0, 10.0)]
ASKS = [(100.1, 1.0), (100.4, 2.0), (102.0, 10.0)]


def test_depth_within_band() -> None:
    notional, truncated = m.depth_within(BIDS, 100.0, 1.0, "bid")  # limite 99.0
    assert notional == pytest.approx(99.9 + 199.0) and not truncated
    notional, truncated = m.depth_within(ASKS, 100.0, 1.0, "ask")  # limite 101.0
    assert notional == pytest.approx(100.1 + 200.8) and not truncated


def test_depth_truncated_when_all_visible_levels_inside_band() -> None:
    notional, truncated = m.depth_within(BIDS, 100.0, 5.0, "bid")
    assert notional == pytest.approx(99.9 + 199.0 + 980.0) and truncated
    assert m.depth_within([], 100.0, 1.0, "ask") == (0.0, False)
    with pytest.raises(ValueError, match="meio"):
        m.depth_within(BIDS, 100.0, 1.0, "meio")


def test_slippage_walks_the_book() -> None:
    # comprar 200 USDT: 100.1 (1 un = 100.1 USDT) + 99.9 USDT a 100.4
    qty = 1.0 + 99.9 / 100.4
    vwap = 200.0 / qty
    assert m.slippage_bps(ASKS, 100.0, 200.0, "buy") == pytest.approx((vwap - 100) / 100 * 1e4)
    assert m.slippage_bps(ASKS, 100.0, 50.0, "buy") == pytest.approx(10.0)  # só o 1º nível
    assert m.slippage_bps(BIDS, 100.0, 50.0, "sell") == pytest.approx(10.0)
    assert m.slippage_bps(ASKS, 100.0, 1e9, "buy") is None  # livro visível insuficiente
    assert m.slippage_bps(ASKS, 100.0, 0.0, "buy") is None


def test_returns() -> None:
    closes = [100.0, 101.0, 102.0, 99.0]
    assert m.simple_return(closes, 3) == pytest.approx(-0.01)
    assert m.simple_return(closes, 4) is None
    assert m.log_returns([100.0, 110.0]) == [pytest.approx(math.log(1.1))]


def test_zscore_of_last_return() -> None:
    closes = [100.0]
    for i in range(60):  # alterna +1% / -1% → desvio-padrão conhecido
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 1 / 1.01))
    closes.append(closes[-1] * 1.05)  # salto de 5%
    z = m.return_zscore(closes)
    assert z is not None and z == pytest.approx(math.log(1.05) / math.log(1.01), rel=1e-6)
    assert m.return_zscore(closes[:20]) is None  # histórico insuficiente
    assert m.return_zscore([100.0] * 50) is None  # desvio zero


def test_relative_volume_uses_median() -> None:
    volumes = [10.0] * 59 + [1000.0] + [50.0]  # um outlier não distorce a mediana
    assert m.relative_volume(volumes) == pytest.approx(5.0)
    assert m.relative_volume([0.0] * 30 + [5.0]) is None
    assert m.relative_volume([1.0] * 5) is None


def test_realized_vol_annualized() -> None:
    closes = [100.0]
    for i in range(61):
        closes.append(closes[-1] * (1.001 if i % 2 == 0 else 1 / 1.001))
    rv = m.realized_vol(closes, 60)
    rets = m.log_returns(closes)[-60:]
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    assert rv == pytest.approx(sd * math.sqrt(525_600))
    assert m.realized_vol(closes[:10], 60) is None
