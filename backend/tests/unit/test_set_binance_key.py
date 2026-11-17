"""Script de setup da chave: o valor gravado precisa ser lido de volta pela configuração."""

from __future__ import annotations

import importlib.util
from types import ModuleType

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from quantum_one.core.config import load_settings
from tests.conftest import REPO_ROOT


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "set_binance_key", REPO_ROOT / "infra/scripts/set_binance_key.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pem() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_round_trip_through_settings(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    pem = _pem()
    env = mod.update_env(
        "QONE_ENV=prod\nBINANCE_API_KEY=__placeholder__\nBINANCE_API_SECRET=__placeholder__\n",
        "A" * 64,
        mod.pem_to_env_value(pem),
    )
    lines = dict(line.split("=", 1) for line in env.splitlines())
    assert lines["QONE_ENV"] == "prod" and lines["BINANCE_API_KEY"] == "A" * 64
    assert "\n" not in lines["BINANCE_API_SECRET"]  # uma linha só no .env
    # Docker Compose remove as aspas; a configuração desfaz os \n
    monkeypatch.setenv("BINANCE_API_KEY", lines["BINANCE_API_KEY"])
    monkeypatch.setenv("BINANCE_API_SECRET", lines["BINANCE_API_SECRET"].strip('"'))
    s = load_settings()
    assert s.binance_api_secret is not None
    assert s.binance_api_secret.get_secret_value() == pem.strip()


def test_missing_lines_are_appended() -> None:
    env = _load().update_env("X=1\n", "K" * 30, '"v"')
    assert env.splitlines() == ["X=1", "BINANCE_API_KEY=" + "K" * 30, 'BINANCE_API_SECRET="v"']


def test_rejects_non_pem_and_rsa_sized() -> None:
    mod = _load()
    with pytest.raises(ValueError, match="PEM"):
        mod.pem_to_env_value("não é chave")
    with pytest.raises(ValueError, match="RSA"):
        mod.pem_to_env_value(
            "-----BEGIN PRIVATE KEY-----\n" + "A" * 1600 + "\n-----END PRIVATE KEY-----"
        )
