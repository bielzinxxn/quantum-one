from __future__ import annotations

import pytest

from quantum_one.services import cli
from quantum_one.services.registry import SERVICES


def test_registry_has_all_workers() -> None:
    assert set(SERVICES) == {"marketdata", "engine", "trader", "accounting"}


def test_trader_starts_blocked() -> None:
    assert SERVICES["trader"].extra_health["trading_state"] == "BLOCKED"


def test_unknown_service_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["nope"]) == 2
    assert "uso:" in capsys.readouterr().err


def test_invalid_config_exit_78_without_leaking(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "tiny-secret")
    assert cli.main(["engine"]) == cli.EXIT_CONFIG_ERROR
    err = capsys.readouterr().err
    assert "postgres_password" in err
    assert "tiny-secret" not in err
