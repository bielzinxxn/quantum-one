"""Política de permissões da chave de API (fail-closed, ADR-008 §2)."""

from __future__ import annotations

from quantum_one.core.config import KeyPolicy
from quantum_one.exchange.models import KeyPermissions

# permissões que NUNCA podem estar ligadas, em nenhuma fase
_ALWAYS_FORBIDDEN = {
    "enable_withdrawals": "saque habilitado",
    "enable_internal_transfer": "transferência interna habilitada",
    "permits_universal_transfer": "transferência universal habilitada",
    "enable_margin": "margem habilitada",
    "enable_futures": "futuros habilitados",
    "enable_vanilla_options": "opções habilitadas",
    "enable_portfolio_margin_trading": "portfolio margin habilitado",
}


def evaluate(perms: KeyPermissions, policy: KeyPolicy, require_ip_restrict: bool) -> list[str]:
    """Retorna a lista de violações. Lista vazia = chave aprovada."""
    violations = [msg for attr, msg in _ALWAYS_FORBIDDEN.items() if getattr(perms, attr)]
    if not perms.enable_reading:
        violations.append("leitura desabilitada (enableReading=false)")
    if policy is KeyPolicy.READ_ONLY and perms.enable_spot_and_margin_trading:
        violations.append("chave com permissão de trading, mas a política é read_only")
    if policy is KeyPolicy.TRADE and not perms.enable_spot_and_margin_trading:
        violations.append("política trade exige enableSpotAndMarginTrading=true")
    if require_ip_restrict and not perms.ip_restrict:
        violations.append("chave sem restrição de IP (ipRestrict=false)")
    return violations
