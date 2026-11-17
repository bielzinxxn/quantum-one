"""Mascaramento de segredos em estruturas de log.

Duas camadas:
1. chaves com nome sensível (password, secret, token, signature, ...) têm o valor trocado;
2. valores secretos conhecidos (vindos da configuração) são removidos de qualquer string.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

MASK = "***"

SENSITIVE_KEY = re.compile(
    r"(pass(word|wd)?|secret|token|api[_-]?key|apikey|signature|listen[_-]?key|"
    r"authorization|cookie|totp|private[_-]?key|dsn)",
    re.IGNORECASE,
)
# Credenciais embutidas em URLs: scheme://user:senha@host
URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<user>[^:/@\s]+):[^@/\s]+@", re.I)


class Redactor:
    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        # ignora valores muito curtos para não mascarar texto comum por acidente
        self._secrets = sorted({s for s in secret_values if len(s) >= 6}, key=len, reverse=True)

    def redact_str(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, MASK)
        return URL_CREDENTIALS.sub(rf"\g<scheme>\g<user>:{MASK}@", text)

    def redact(self, value: Any, depth: int = 0) -> Any:
        if depth > 12:
            return MASK  # estrutura profunda demais: não arriscar
        if isinstance(value, str):
            return self.redact_str(value)
        if isinstance(value, Mapping):
            return {
                k: (
                    MASK
                    if isinstance(k, str) and SENSITIVE_KEY.search(k)
                    else self.redact(v, depth + 1)
                )
                for k, v in value.items()
            }
        if isinstance(value, list | tuple | set):
            return [self.redact(v, depth + 1) for v in value]
        if isinstance(value, bytes | bytearray):
            return f"<{len(value)} bytes>"
        if isinstance(value, int | float | bool) or value is None:
            return value
        return self.redact_str(repr(value))
