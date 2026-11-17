"""Configuração validada a partir de variáveis de ambiente.

Regras de segurança aplicadas aqui (fail-fast no boot):
- senhas de banco/Redis ausentes ou com placeholder são rejeitadas;
- modo `live` exige `LIVE_TRADING_ENABLED=true` explícito;
- chaves da Binance com placeholder são tratadas como ausentes.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cached_property

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_MARKERS = ("__placeholder__", "__generate__", "change-me", "changeme")


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered == "" or any(marker in lowered for marker in PLACEHOLDER_MARKERS)


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class TradingMode(StrEnum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class KeyPolicy(StrEnum):
    READ_ONLY = "read_only"  # Fases 3–11: chave sem permissão de trading
    TRADE = "trade"  # só para live, com liberação explícita


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="", extra="ignore", frozen=True, hide_input_in_errors=True
    )

    qone_env: Environment = Environment.DEV
    service_name: str = Field(default="unknown", min_length=1, max_length=64)
    log_level: str = "INFO"

    trading_mode: TradingMode = TradingMode.BACKTEST
    live_trading_enabled: bool = False

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "quantum_one"
    postgres_user: str
    postgres_password: SecretStr

    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_password: SecretStr

    health_host: str = "0.0.0.0"  # noqa: S104 — só dentro da rede do contêiner
    health_port: int = Field(default=8080, ge=1, le=65535)
    health_check_interval_s: float = Field(default=5.0, gt=0)
    watchdog_timeout_s: float = Field(default=60.0, gt=0)

    binance_api_key: SecretStr | None = None
    # HMAC (string) ou Ed25519 (PEM; aceita "\\n" escapado numa linha só)
    binance_api_secret: SecretStr | None = None
    binance_key_policy: KeyPolicy = KeyPolicy.READ_ONLY
    binance_testnet: bool = False
    binance_recv_window_ms: int = Field(default=5000, ge=1000, le=60000)
    clock_max_offset_ms: int = Field(default=1000, ge=50, le=5000)
    weight_budget_ratio: float = Field(default=0.8, gt=0.1, le=0.95)
    account_poll_s: float = Field(default=60.0, ge=10.0)
    instruments_sync_s: float = Field(default=3600.0, ge=60.0)

    # --- Market Scanner (Fase 4) ---
    binance_ws_url: str | None = None  # padrão: stream.binance.com:9443 (ou testnet)
    scanner_universe_size: int = Field(default=30, ge=1, le=300)
    scanner_min_quote_volume: float = Field(default=5_000_000.0, ge=0)
    scanner_extra_symbols: str = ""  # CSV, sempre incluídos se negociáveis
    scanner_excluded_bases: str = "USDC,FDUSD,TUSD,USDP,DAI,BUSD,EUR,TRY,BRL,AEUR,USD1,PAXG"
    scanner_universe_refresh_s: float = Field(default=3600.0, ge=300.0)
    scanner_stale_after_s: float = Field(default=10.0, ge=3.0, le=120.0)
    scanner_snapshot_interval_s: float = Field(default=5.0, ge=1.0, le=60.0)
    scanner_ws_rotate_after_s: float = Field(default=84_600.0, ge=600.0, le=86_000.0)
    scanner_warmup_candles: int = Field(default=1000, ge=60, le=1000)
    scanner_slippage_probe_quote: float = Field(default=1000.0, gt=0)

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, v: str) -> str:
        level = v.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"LOG_LEVEL inválido: {v}")
        return level

    @field_validator("postgres_password", "redis_password")
    @classmethod
    def _no_placeholder_passwords(cls, v: SecretStr) -> SecretStr:
        if is_placeholder(v.get_secret_value()):
            raise ValueError("senha ausente ou placeholder — rode `make env`")
        if len(v.get_secret_value()) < 16:
            raise ValueError("senha curta demais (mínimo 16 caracteres)")
        return v

    @field_validator("binance_api_key", "binance_api_secret")
    @classmethod
    def _placeholder_key_is_absent(cls, v: SecretStr | None) -> SecretStr | None:
        if v is None or is_placeholder(v.get_secret_value()):
            return None
        raw = v.get_secret_value().strip()
        if "PRIVATE KEY" in raw and "\n" not in raw:
            raw = raw.replace("\\n", "\n")  # PEM escapado numa linha do .env
        return SecretStr(raw)

    @model_validator(mode="after")
    def _live_requires_explicit_enable(self) -> Settings:
        if self.trading_mode is TradingMode.LIVE and not self.live_trading_enabled:
            raise ValueError("TRADING_MODE=live exige LIVE_TRADING_ENABLED=true explícito")
        if self.trading_mode is TradingMode.LIVE and self.qone_env is not Environment.PROD:
            raise ValueError("TRADING_MODE=live só é permitido com QONE_ENV=prod")
        if self.binance_key_policy is KeyPolicy.TRADE and self.trading_mode is not TradingMode.LIVE:
            raise ValueError("BINANCE_KEY_POLICY=trade só é permitido com TRADING_MODE=live")
        return self

    @property
    def ws_base_url(self) -> str:
        if self.binance_ws_url:
            return self.binance_ws_url.rstrip("/")
        if self.binance_testnet:
            return "wss://stream.testnet.binance.vision"
        return "wss://stream.binance.com:9443"

    @staticmethod
    def _csv(value: str) -> tuple[str, ...]:
        return tuple(v.strip().upper() for v in value.split(",") if v.strip())

    @property
    def extra_symbols(self) -> tuple[str, ...]:
        return self._csv(self.scanner_extra_symbols)

    @property
    def excluded_bases(self) -> frozenset[str]:
        return frozenset(self._csv(self.scanner_excluded_bases))

    @property
    def has_binance_credentials(self) -> bool:
        return self.binance_api_key is not None and self.binance_api_secret is not None

    @cached_property
    def secret_values(self) -> tuple[str, ...]:
        """Valores sensíveis a serem mascarados em qualquer log."""
        secrets = [self.postgres_password, self.redis_password]
        secrets += [s for s in (self.binance_api_key, self.binance_api_secret) if s]
        values = [s.get_secret_value() for s in secrets]
        # cada linha do PEM também é segredo (logs podem quebrar o texto em linhas)
        for value in list(values):
            values += [line for line in value.splitlines() if "-----" not in line]
        return tuple(values)


def load_settings() -> Settings:
    return Settings()  # campos obrigatórios vêm do ambiente
