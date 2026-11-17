"""Registro dos workers. Cada fase troca o `work` padrão pela lógica real."""

from __future__ import annotations

from quantum_one.services.account_sync import account_work
from quantum_one.services.marketdata_work import marketdata_work
from quantum_one.services.runtime import ServiceSpec

SERVICES: dict[str, ServiceSpec] = {
    "marketdata": ServiceSpec(name="marketdata", work=marketdata_work),
    "engine": ServiceSpec(name="engine"),
    # fail-closed: o trader nasce BLOQUEADO; só a reconciliação (Fase 8) poderá liberar
    "trader": ServiceSpec(
        name="trader", work=account_work, extra_health={"trading_state": "BLOCKED"}
    ),
    "accounting": ServiceSpec(name="accounting"),
}
