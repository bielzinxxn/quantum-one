"""Nomes de stream e URL do stream combinado."""

from __future__ import annotations

from collections.abc import Sequence

MAX_STREAMS_PER_CONNECTION = 1024  # limite documentado
STREAMS_PER_SYMBOL = ("kline_1m", "bookTicker", "depth20")


def stream_names(symbols: Sequence[str]) -> list[str]:
    return [f"{s.lower()}@{kind}" for s in symbols for kind in STREAMS_PER_SYMBOL]


def combined_url(base: str, symbols: Sequence[str]) -> str:
    names = stream_names(symbols)
    if not names:
        raise ValueError("universo vazio")
    if len(names) > MAX_STREAMS_PER_CONNECTION:
        raise ValueError(f"{len(names)} streams > limite de {MAX_STREAMS_PER_CONNECTION}")
    return f"{base}/stream?streams={'/'.join(names)}"
