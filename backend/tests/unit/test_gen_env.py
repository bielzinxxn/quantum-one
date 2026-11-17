from __future__ import annotations

import importlib.util
import stat
from pathlib import Path
from types import ModuleType

from tests.conftest import REPO_ROOT


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_env", REPO_ROOT / "infra/scripts/gen_env.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generates_unique_strong_secrets_with_mode_600(tmp_path: Path) -> None:
    gen = _load()
    (tmp_path / ".env.example").write_text(
        "# PASSWORD=__generate__ (comentário fica)\nA=__generate__\nB=__generate__\n"
        "KEY=__placeholder__\nMODE=backtest\n"
    )
    assert gen.main(["x", str(tmp_path)]) == 0
    env_file = tmp_path / ".env"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    values = dict(
        line.split("=", 1)
        for line in env_file.read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert values["A"] != values["B"]
    assert len(values["A"]) >= 40 and "__generate__" not in values["A"]
    assert values["KEY"] == "__placeholder__"
    assert values["MODE"] == "backtest"
    assert "# PASSWORD=__generate__" in env_file.read_text()


def test_refuses_to_overwrite(tmp_path: Path) -> None:
    gen = _load()
    (tmp_path / ".env.example").write_text("A=__generate__\n")
    (tmp_path / ".env").write_text("A=existente\n")
    assert gen.main(["x", str(tmp_path)]) == 1
    assert (tmp_path / ".env").read_text() == "A=existente\n"
