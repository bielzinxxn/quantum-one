from __future__ import annotations

import json

import pytest

from quantum_one.core.logging import configure_logging, get_logger

SECRET = "super-secret-password-123"


def _lines(captured: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in captured.splitlines() if line.strip()]


def test_json_output_with_service_and_timestamp(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("engine", "INFO")
    get_logger().info("hello", x=1)
    (line,) = _lines(capsys.readouterr().out)
    assert line["event"] == "hello"
    assert line["service"] == "engine"
    assert line["level"] == "info"
    assert str(line["timestamp"]).endswith("Z")


def test_secrets_never_reach_output(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("trader", "INFO", [SECRET])
    log = get_logger()
    log.info("connecting", password=SECRET, dsn=f"postgresql://u:{SECRET}@h/db")
    log.info(f"mensagem livre contendo {SECRET}")
    try:
        raise RuntimeError(f"erro com {SECRET}")
    except RuntimeError:
        log.exception("falha")
    out = capsys.readouterr().out
    assert SECRET not in out
    assert len(_lines(out)) == 3


def test_level_filtering(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("engine", "WARNING")
    get_logger().info("invisível")
    get_logger().warning("visível")
    events = [line["event"] for line in _lines(capsys.readouterr().out)]
    assert events == ["visível"]
