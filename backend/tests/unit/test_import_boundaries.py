"""Regras de dependência entre pacotes (docs/02). Cresce junto com o código."""

from __future__ import annotations

import ast
from pathlib import Path

import quantum_one

PKG_ROOT = Path(quantum_one.__file__).parent

# pacote → prefixos que ele NÃO pode importar
FORBIDDEN = {
    "api": ("quantum_one.execution", "quantum_one.exchange", "quantum_one.risk"),
    "core": ("quantum_one.",),  # core não depende de ninguém do projeto além de si
    "analysis": ("quantum_one.execution", "quantum_one.exchange", "quantum_one.db"),
    "strategies": ("quantum_one.execution", "quantum_one.exchange.binance"),
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_forbidden_imports() -> None:
    violations = []
    for pkg, banned in FORBIDDEN.items():
        for file in (PKG_ROOT / pkg).rglob("*.py") if (PKG_ROOT / pkg).exists() else []:
            for name in _imports(file):
                if pkg == "core" and name.startswith("quantum_one.core"):
                    continue
                if any(name.startswith(b) for b in banned):
                    violations.append(f"{file.relative_to(PKG_ROOT)} importa {name}")
    assert not violations, violations
