"""Imprime o /health/ready deste contêiner em JSON legível (usado por `make status`)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def fetch(url: str, timeout_s: float = 3.0) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:  # noqa: S310 — URL local fixa
            body = resp.read()
    except urllib.error.HTTPError as err:  # 503 = não pronto, mas o corpo explica o motivo
        body = err.read()
    except (urllib.error.URLError, OSError) as err:
        return {"erro": f"serviço não respondeu: {err}"}
    data: dict[str, object] = json.loads(body)
    return data


def main() -> int:
    port = os.environ.get("HEALTH_PORT", "8080")
    print(json.dumps(fetch(f"http://127.0.0.1:{port}/health/ready"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
