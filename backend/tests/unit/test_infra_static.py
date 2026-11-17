"""Checagens estáticas de segurança da infraestrutura (rodam sem Docker)."""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from tests.conftest import REPO_ROOT

APPS = ("migrate", "marketdata", "engine", "trader", "accounting", "api")


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
    return data


def test_images_pinned_by_digest(compose: dict[str, Any]) -> None:
    for name in ("postgres", "redis"):
        assert "@sha256:" in compose["services"][name]["image"], name
    dockerfile = (REPO_ROOT / "infra/docker/backend.Dockerfile").read_text()
    assert re.search(r"python:3\.12[\w.-]*@sha256:[0-9a-f]{64}", dockerfile)


def test_no_global_env_file(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        assert "env_file" not in svc, name


def test_binance_keys_only_in_trader(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        env = svc.get("environment", {}) or {}
        has_key = any(k.startswith("BINANCE_API_") for k in env)
        assert has_key == (name == "trader"), name


def test_internet_only_for_marketdata_and_trader(compose: dict[str, Any]) -> None:
    assert compose["networks"]["internal"]["internal"] is True
    for name, svc in compose["services"].items():
        on_egress = "egress" in svc.get("networks", [])
        assert on_egress == (name in {"marketdata", "trader"}), name


def test_only_api_publishes_port_on_loopback(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        ports = svc.get("ports", [])
        if name == "api":
            assert ports and all(str(p).startswith("127.0.0.1:") for p in ports)
        else:
            assert not ports, name


def test_app_containers_hardened(compose: dict[str, Any]) -> None:
    for name in APPS:
        svc = compose["services"][name]
        assert svc["read_only"] is True, name
        assert svc["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in svc["security_opt"], name


def test_each_app_uses_own_db_role(compose: dict[str, Any]) -> None:
    roles = {compose["services"][n]["environment"]["POSTGRES_USER"] for n in APPS}
    assert len(roles) == len(APPS)
    assert "postgres" not in roles


def test_restart_and_log_rotation(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        if name != "migrate":
            assert svc["restart"] == "unless-stopped", name
        assert svc["logging"]["options"]["max-size"], name


def test_env_example_has_no_real_secrets() -> None:
    sensitive = re.compile(r"(PASSWORD|SECRET|_KEY|TOKEN)$", re.I)
    for line in (REPO_ROOT / ".env.example").read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if sensitive.search(key):
            assert value in {"__generate__", "__placeholder__"}, key


def test_gitignore_and_dockerignore_exclude_env() -> None:
    for f in (".gitignore", ".dockerignore"):
        assert ".env" in (REPO_ROOT / f).read_text().splitlines(), f


def test_redis_conf_safe() -> None:
    conf = (REPO_ROOT / "infra/redis/redis.conf").read_text()
    assert "appendonly yes" in conf
    assert "maxmemory-policy noeviction" in conf
    for cmd in ("FLUSHALL", "CONFIG", "KEYS"):
        assert f'rename-command {cmd} ""' in conf
