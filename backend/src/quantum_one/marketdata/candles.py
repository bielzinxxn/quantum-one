"""Série de velas fechadas por símbolo: ordenada, sem duplicatas, com detecção de lacunas."""

from __future__ import annotations

import bisect

from quantum_one.marketdata.models import ONE_MINUTE_MS, Candle


class CandleSeries:
    def __init__(self, symbol: str, maxlen: int = 1440, step_ms: int = ONE_MINUTE_MS) -> None:
        self.symbol = symbol
        self._maxlen = maxlen
        self._step = step_ms
        self._times: list[int] = []
        self._by_time: dict[int, Candle] = {}

    def __len__(self) -> int:
        return len(self._times)

    @property
    def last_open_time(self) -> int | None:
        return self._times[-1] if self._times else None

    def add(self, candle: Candle) -> bool:
        """Insere/atualiza. Retorna True se a vela é nova (não vista antes)."""
        if candle.symbol != self.symbol:
            raise ValueError(f"vela de {candle.symbol} na série de {self.symbol}")
        t = candle.open_time_ms
        is_new = t not in self._by_time
        if is_new:
            if len(self._times) >= self._maxlen and t < self._times[0]:
                return False  # mais antiga que a janela mantida
            bisect.insort(self._times, t)
        self._by_time[t] = candle
        while len(self._times) > self._maxlen:
            del self._by_time[self._times.pop(0)]
        return is_new

    def gap_after_last(self, next_open_ms: int) -> tuple[int, int] | None:
        """Intervalo [início, fim) faltante entre a última vela e `next_open_ms`."""
        last = self.last_open_time
        if last is None or next_open_ms <= last + self._step:
            return None
        return last + self._step, next_open_ms

    def candles(self) -> list[Candle]:
        return [self._by_time[t] for t in self._times]

    def closes(self) -> list[float]:
        return [float(self._by_time[t].close) for t in self._times]

    def quote_volumes(self) -> list[float]:
        return [float(self._by_time[t].quote_volume) for t in self._times]

    def internal_gaps(self) -> int:
        """Quantas velas faltam dentro da janela mantida (deve ser 0 após o backfill)."""
        if len(self._times) < 2:
            return 0
        expected = (self._times[-1] - self._times[0]) // self._step + 1
        return int(expected - len(self._times))
