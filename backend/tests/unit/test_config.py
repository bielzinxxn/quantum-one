from __future__ import annotations

import pytest
from pydantic import ValidationError

from quantum_one.core.config import Environment, TradingMode, is_placeholder, load_settings


def test_valid_defaults(valid_env: dict[str, str]) -> None:
    s = load_settings()
    assert s.trading_mode is TradingMode.BACKTEST
    assert s.live_trading_enabled is False
    assert s.has_binance_credentials is False
    assert valid_env["POSTGRES_PASSWORD"] in s.secret_values


@pytest.mark.parametrize("value", ["__generate__", "__placeholder__", "change-me-please-xxxxx", ""])
def test_placeholder_password_rejected(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", value)
    with pytest.raises(ValidationError, match="postgres_password"):
        load_settings()


def test_short_password_rejected(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_PASSWORD", "curta")
    with pytest.raises(ValidationError, match="curta demais"):
        load_settings()


def test_missing_password_rejected(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD")
    with pytest.raises(ValidationError):
        load_settings()


def test_live_requires_explicit_flag(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("QONE_ENV", "prod")
    with pytest.raises(ValidationError, match="LIVE_TRADING_ENABLED"):
        load_settings()


def test_live_forbidden_outside_prod(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("QONE_ENV", "dev")
    with pytest.raises(ValidationError, match="QONE_ENV=prod"):
        load_settings()


def test_live_allowed_with_flag_in_prod(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("QONE_ENV", "prod")
    s = load_settings()
    assert s.trading_mode is TradingMode.LIVE
    assert s.qone_env is Environment.PROD


def test_binance_placeholder_is_absent(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "__placeholder__")
    monkeypatch.setenv("BINANCE_API_SECRET", "__placeholder__")
    s = load_settings()
    assert s.binance_api_key is None
    assert s.has_binance_credentials is False


def test_binance_real_key_is_secret(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "fake-key-abcdefghijkl")
    monkeypatch.setenv("BINANCE_API_SECRET", "fake-secret-abcdefghijkl")
    s = load_settings()
    assert s.has_binance_credentials
    assert "fake-secret-abcdefghijkl" in s.secret_values
    assert "fake-secret" not in repr(s)  # SecretStr nunca aparece em repr


def test_invalid_log_level(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ValidationError, match="LOG_LEVEL"):
        load_settings()


def test_log_level_normalized(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert load_settings().log_level == "DEBUG"


def test_validation_error_never_echoes_secret(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "tiny-secret")
    with pytest.raises(ValidationError) as exc:
        load_settings()
    assert "tiny-secret" not in str(exc.value)


def test_is_placeholder() -> None:
    assert is_placeholder("  ")
    assert is_placeholder("CHANGEME")
    assert not is_placeholder("Xk9_real-looking-value")


ED_PEM = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MC4CAQAwBQYDK2VwBCIEIFakeFakeFakeFakeFakeFakeFakeFakeFake12\n"
    "-----END PRIVATE KEY-----"
)


def test_escaped_pem_secret_is_unescaped(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "fake-key-abcdefghijkl")
    monkeypatch.setenv("BINANCE_API_SECRET", ED_PEM.replace("\n", "\\n"))
    s = load_settings()
    assert s.binance_api_secret is not None
    assert s.binance_api_secret.get_secret_value() == ED_PEM
    # a linha base64 do PEM também é mascarada nos logs
    assert ED_PEM.splitlines()[1] in s.secret_values


def test_trade_key_policy_requires_live(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINANCE_KEY_POLICY", "trade")
    with pytest.raises(ValidationError, match="BINANCE_KEY_POLICY=trade"):
        load_settings()


def test_recv_window_bounds(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings().binance_recv_window_ms == 5000
    monkeypatch.setenv("BINANCE_RECV_WINDOW_MS", "70000")
    with pytest.raises(ValidationError):
        load_settings()


def test_scanner_settings_and_ws_url(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    s = load_settings()
    assert s.ws_base_url == "wss://stream.binance.com:9443"
    assert "USDC" in s.excluded_bases and s.extra_symbols == ()
    monkeypatch.setenv("BINANCE_TESTNET", "true")
    assert load_settings().ws_base_url == "wss://stream.testnet.binance.vision"
    monkeypatch.setenv("BINANCE_WS_URL", "wss://data-stream.binance.vision/")
    monkeypatch.setenv("SCANNER_EXTRA_SYMBOLS", " pepeusdt, ,BONKUSDT")
    s = load_settings()
    assert s.ws_base_url == "wss://data-stream.binance.vision"
    assert s.extra_symbols == ("PEPEUSDT", "BONKUSDT")
    monkeypatch.setenv("SCANNER_STALE_AFTER_S", "1")
    with pytest.raises(ValidationError):
        load_settings()
