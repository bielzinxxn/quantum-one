from __future__ import annotations

from fastapi.testclient import TestClient

from quantum_one.api.app import create_app
from quantum_one.core.config import load_settings


async def _ok() -> None:
    return None


async def _down() -> None:
    raise ConnectionError


def test_live_and_ready_ok(valid_env: dict[str, str]) -> None:
    app = create_app(load_settings(), checks={"postgres": _ok, "redis": _ok})
    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"service": "api", "alive": True}
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True


def test_ready_503_when_dependency_down(valid_env: dict[str, str]) -> None:
    app = create_app(load_settings(), checks={"postgres": _ok, "redis": _down})
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json()["checks"]["redis"]["ok"] is False


def test_no_public_docs(valid_env: dict[str, str]) -> None:
    app = create_app(load_settings(), checks={})
    with TestClient(app) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
