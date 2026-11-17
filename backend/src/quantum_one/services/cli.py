"""Ponto de entrada comum: `python -m quantum_one.services.cli <serviço>`."""

from __future__ import annotations

import asyncio
import sys

from pydantic import ValidationError

from quantum_one.core.config import load_settings
from quantum_one.services.registry import SERVICES
from quantum_one.services.runtime import run_service

EXIT_CONFIG_ERROR = 78  # EX_CONFIG


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in SERVICES:
        sys.stderr.write(f"uso: cli <{'|'.join(sorted(SERVICES))}>\n")
        return 2
    try:
        settings = load_settings()
    except ValidationError as exc:
        # mostra só campo e motivo — nunca o valor recebido
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"]) or "config"
            sys.stderr.write(f"config inválida: {field}: {err['msg']}\n")
        return EXIT_CONFIG_ERROR
    asyncio.run(run_service(SERVICES[args[0]], settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
