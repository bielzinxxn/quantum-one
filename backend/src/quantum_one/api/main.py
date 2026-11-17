"""Entrypoint da API: `python -m quantum_one.api.main`."""

from __future__ import annotations

import sys

import uvicorn
from pydantic import ValidationError

from quantum_one.api.app import create_app
from quantum_one.core.config import load_settings


def main() -> int:
    try:
        settings = load_settings()
    except ValidationError as exc:
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"]) or "config"
            sys.stderr.write(f"config inválida: {field}: {err['msg']}\n")
        return 78
    uvicorn.run(
        create_app(settings),
        host=settings.health_host,
        port=settings.health_port,
        log_level=settings.log_level.lower(),
        access_log=False,
        server_header=False,
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
