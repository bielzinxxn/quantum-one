"""Healthcheck do Docker sem curl: `python -m quantum_one.services.healthcheck [path]`.

Sai com 0 se HTTP 200, 1 caso contrário.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request


def check(url: str, timeout_s: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:  # noqa: S310 — URL local fixa
            return bool(resp.status == 200)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = args[0] if args else "/health/live"
    port = os.environ.get("HEALTH_PORT", "8080")
    return 0 if check(f"http://127.0.0.1:{port}{path}") else 1


if __name__ == "__main__":
    raise SystemExit(main())
