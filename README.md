# QUANTUM ONE

Infraestrutura proprietária de trading quantitativo (Binance spot).

Documentação em [`docs/`](docs/README.md); estado atual em [`docs/ESTADO_DO_PROJETO.md`](docs/ESTADO_DO_PROJETO.md).

> **Primeira vez?** No seu Windows (grátis, para validar): [guia Windows](docs/GUIA_WINDOWS_LOCAL.md) · Numa VPS (24/7): [guia VPS](docs/GUIA_PASSO_A_PASSO.md).

## Pré-requisitos
- Docker Engine 24+ com Compose v2
- Python 3.12+ e [uv](https://docs.astral.sh/uv/) (só para rodar testes e lint fora do Docker)

## Primeira execução
```bash
make env        # cria .env com senhas aleatórias (permissão 600); não sobrescreve
make build      # compila a imagem do backend
make up         # sobe a stack e espera tudo ficar healthy
make ps         # estado de cada contêiner
```

## Testes
```bash
make check             # ruff + mypy --strict + testes unitários (sem Docker)
make test-integration  # Postgres/Redis reais (sobe a stack dev)
make smoke             # stack completa: saúde, rede, segredos, autorreinício
```

## Binance (somente leitura, Fase 3)
Crie a chave seguindo `infra/vps/SETUP.md` §8 (Ed25519, só leitura, IP restrito) e valide:
```bash
make check-binance     # relógio, permissões da chave, saldos, ordens abertas, comissões
```

## Operação
```bash
make logs s=trader     # logs de um serviço
make backup            # dump do Postgres em ./backups (cifrado se AGE_RECIPIENT definido)
make down              # para a stack (dados preservados)
```

## Serviços (Fase 4: leitura da exchange + Market Scanner; nenhuma ordem é enviada)
| Serviço | Rede | Função nesta fase |
|---|---|---|
| postgres, redis | internal | persistência e barramento |
| migrate | internal | `alembic upgrade head` e sai |
| marketdata | internal + egress | instrumentos (1 h) + **Market Scanner**: WebSocket de kline/livro dos ~30 pares USDT mais líquidos, backfill, métricas → `md:candles`, `md:scanner`, `md:health` |
| trader | internal + egress | valida a chave, mede o relógio, lê saldos e ordens a cada 60 s |
| engine, accounting | internal | saúde; sem internet |
| api | internal + edge | saúde em `127.0.0.1:8000/health/ready` |

O `trader` nasce **BLOQUEADO** (`trading_state=BLOCKED`) e só uma reconciliação futura poderá liberá-lo.
