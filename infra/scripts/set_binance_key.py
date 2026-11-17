#!/usr/bin/env python3
"""Grava a chave da Binance no .env sem editar o arquivo à mão.

Uso (na pasta do projeto, na VPS):
    python3 infra/scripts/set_binance_key.py ~/binance-keys/private.pem

- Pede a API KEY (o código que a Binance mostra) sem ecoar na tela.
- Lê a chave PRIVADA Ed25519 do arquivo .pem e grava numa linha só, no formato esperado.
- Nunca imprime segredos. Mantém o .env com permissão 600.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path


def pem_to_env_value(pem: str) -> str:
    text = pem.strip()
    if "BEGIN PRIVATE KEY" not in text or "END PRIVATE KEY" not in text:
        raise ValueError("o arquivo não parece uma chave privada PEM (BEGIN PRIVATE KEY)")
    if len(text) > 120:
        raise ValueError(
            "chave longa demais para Ed25519 (é RSA?). Gere com: "
            "openssl genpkey -algorithm ed25519 -out private.pem"
        )
    return '"' + text.replace("\n", "\\n") + '"'


def update_env(env_text: str, api_key: str, secret_value: str) -> str:
    found = {"BINANCE_API_KEY": False, "BINANCE_API_SECRET": False}
    out = []
    for line in env_text.splitlines():
        key = line.split("=", 1)[0].strip()
        if key == "BINANCE_API_KEY":
            line, found[key] = f"BINANCE_API_KEY={api_key}", True
        elif key == "BINANCE_API_SECRET":
            line, found[key] = f"BINANCE_API_SECRET={secret_value}", True
        out.append(line)
    for key, ok in found.items():
        if not ok:
            out.append(f"{key}={api_key if key == 'BINANCE_API_KEY' else secret_value}")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("uso: python3 infra/scripts/set_binance_key.py CAMINHO/private.pem\n")
        return 2
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.exists():
        sys.stderr.write("não achei o .env — rode antes: make env\n")
        return 1
    try:
        secret_value = pem_to_env_value(Path(argv[1]).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"erro na chave privada: {exc}\n")
        return 1
    api_key = getpass.getpass("Cole a API KEY da Binance (não aparece na tela) e Enter: ").strip()
    if len(api_key) < 20 or any(c.isspace() for c in api_key):
        sys.stderr.write("API KEY inválida (vazia, curta ou com espaços). Nada foi alterado.\n")
        return 1
    new_text = update_env(env_path.read_text(encoding="utf-8"), api_key, secret_value)
    tmp = env_path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    os.replace(tmp, env_path)
    print("Chave gravada no .env (permissão 600). Agora rode: make up && make check-binance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
