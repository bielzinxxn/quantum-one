# 02 — Estrutura de diretórios

Monorepo. Arquivos curtos, um conceito por arquivo. Os serviços são pontos de entrada finos sobre os pacotes de domínio, de modo que backtest, paper e live importam o mesmo código.

```text
quantum-one/
├── CLAUDE.md
├── README.md
├── .env.example                 # só placeholders
├── .gitignore                   # inclui .env, data/, *.parquet
├── Makefile                     # make up / test / lint / backtest
├── docker-compose.yml           # produção (VPS)
├── docker-compose.dev.yml       # overrides locais
│
├── docs/
│   ├── ESTADO_DO_PROJETO.md     # fonte de verdade entre sessões (≤25 linhas)
│   ├── 01-arquitetura.md … 08-testes.md
│   └── decisoes/                # ADRs
│
├── backend/
│   ├── pyproject.toml           # deps fixadas; ruff, mypy --strict, pytest
│   ├── alembic.ini
│   ├── migrations/              # Alembic
│   ├── src/quantum_one/
│   │   ├── core/                # config (pydantic-settings), logging (structlog),
│   │   │                        # clock, ids (uuid7), money (Decimal), errors
│   │   ├── contracts/           # schemas Pydantic dos eventos e enums compartilhados
│   │   ├── bus/                 # Redis Streams: publisher, consumer group, dedup
│   │   ├── db/                  # engine asyncpg/SQLAlchemy Core, repositórios
│   │   ├── exchange/
│   │   │   ├── gateway.py       # interface ReadOnlyGateway (Protocol)
│   │   │   ├── models.py errors.py clock.py key_policy.py
│   │   │   ├── binance/         # client (CCXT), gateway, parsers, filters
│   │   │   ├── paper/           # simulador ao vivo (book real, parciais, latência)
│   │   │   ├── sim/             # simulador do backtest
│   │   │   └── rate_limit.py    # limitador por peso
│   │   ├── contracts/           # envelope de eventos + payloads (market.py)
│   │   ├── marketdata/          # connection (WS), messages, candles, backfill,
│   │   │                        # metrics, universe, scanner (estado + flags)
│   │   ├── analysis/
│   │   │   ├── indicators/      # rsi, macd, vwap, ema, atr, bollinger, vol_profile…
│   │   │   └── regime/          # classificador determinístico + versão
│   │   ├── strategies/          # base, momentum, mean_reversion, breakout,
│   │   │                        # liquidity, memecoin_filter
│   │   ├── backtest/            # engine, cost_model, walk_forward, edge_gate, benchmark
│   │   ├── risk/                # limits, sizing (ATR/Kelly/teto), kill_switch,
│   │   │                        # correlation, drawdown_scaler, trade_budget
│   │   ├── allocation/          # pesos entre estratégias (mín./máx.)
│   │   ├── execution/           # order_manager, idempotency, state machine,
│   │   │                        # reconciliation
│   │   ├── accounting/          # ledger, pnl, equity/hwm, attribution, reports,
│   │   │   ├── tax/             # regras BR plugáveis, custo médio, eventos fiscais
│   │   │   └── performance_fee/ # existe, desativado
│   │   ├── monitoring/          # health, alerts, degradation
│   │   ├── api/                 # FastAPI: routers, auth (argon2 + TOTP), schemas
│   │   └── services/            # cli (entrypoint único), registry (workers),
│   │                            # runtime (saúde/watchdog/shutdown), healthcheck
│   └── tests/
│       ├── unit/  property/  integration/  fault/  e2e/
│       └── fixtures/            # respostas gravadas da Binance/CCXT, séries de referência
│
├── frontend/                    # Next.js (App Router) + TS + Tailwind
│   ├── app/                     # overview, live, scanner, strategies, portfolio,
│   │                            # trades, risk, performance, logs, settings
│   ├── components/  lib/api/  lib/charts/
│   └── tests/                   # vitest + Playwright
│
├── infra/
│   ├── docker/                  # Dockerfiles (usuário não root, imagens fixadas)
│   ├── postgres/                # init, parâmetros, script de backup
│   ├── redis/redis.conf         # AOF ligado, sem comandos perigosos
│   └── vps/                     # hardening: ufw, ssh, chrony, fail2ban, tailscale
│
└── data/                        # gitignored: cache Parquet de histórico para backtest
```

**Regra de dependência entre pacotes** (verificada por teste de import):

`core` e `contracts` ← `analysis` ← `strategies` ← `backtest`

`risk`, `allocation`, `execution` e `accounting` dependem de `core`, `contracts` e `exchange.gateway`. Nunca dependem de uma exchange concreta.

`api` só lê o banco e publica comandos. **Não importa** `execution`.
