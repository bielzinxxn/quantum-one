#!/usr/bin/env python3
"""Gera `.env` a partir de `.env.example`, trocando `__generate__` por segredos fortes.

- Nunca sobrescreve um `.env` existente (evita perder senhas já usadas pelo Postgres).
- Cria o arquivo com permissão 600.
- Não imprime nenhum segredo.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

MARKER = "__generate__"


def render(template: str) -> str:
    out = []
    for line in template.splitlines():
        if not line.lstrip().startswith("#") and line.rstrip().endswith("=" + MARKER):
            key = line.split("=", 1)[0]
            line = f"{key}={secrets.token_urlsafe(32)}"
        out.append(line)
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2]
    example, target = root / ".env.example", root / ".env"
    if target.exists():
        sys.stderr.write(".env já existe — não vou sobrescrever. Apague manualmente se for o caso.\n")
        return 1
    content = render(example.read_text(encoding="utf-8"))
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    pending = sum(
        1
        for line in content.splitlines()
        if not line.lstrip().startswith("#") and line.endswith("=__placeholder__")
    )
    print(f".env criado em {target} (permissão 600). Campos __placeholder__ a preencher: {pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
