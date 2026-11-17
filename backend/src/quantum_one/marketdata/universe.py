"""Seleção determinística do universo monitorado (pares USDT mais líquidos)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from quantum_one.exchange.models import Instrument


@dataclass(frozen=True)
class UniverseRules:
    size: int
    min_quote_volume: float
    extra_symbols: tuple[str, ...]
    excluded_bases: frozenset[str]
    quote: str = "USDT"


def select_universe(
    instruments: Iterable[Instrument], quote_volume_24h: Mapping[str, float], rules: UniverseRules
) -> list[str]:
    """Top-N por volume 24h em quote, entre pares negociáveis; extras sempre entram.

    Desempate por símbolo (ordem alfabética) para o resultado ser determinístico.
    """
    eligible = {
        i.symbol: i
        for i in instruments
        if i.tradable and i.quote == rules.quote and i.base not in rules.excluded_bases
    }
    ranked = sorted(
        (s for s in eligible if quote_volume_24h.get(s, 0.0) >= rules.min_quote_volume),
        key=lambda s: (-quote_volume_24h.get(s, 0.0), s),
    )
    chosen = ranked[: rules.size]
    for extra in rules.extra_symbols:
        if extra in eligible and extra not in chosen:
            chosen.append(extra)
    return chosen
