# QUANTUM ONE — comandos do dia a dia. `make help` lista tudo.
SHELL := /bin/bash
COMPOSE := docker compose
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml
BACKEND := cd backend &&

.PHONY: help env build up down ps logs migrate test test-integration lint typecheck check smoke backup check-binance status velas set-binance-key

help: ## lista os comandos
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

env: ## cria .env com segredos aleatórios (não sobrescreve)
	python3 infra/scripts/gen_env.py

build: ## compila a imagem do backend
	$(COMPOSE) build

up: ## sobe a stack e espera todos ficarem saudáveis
	$(COMPOSE) up -d --wait

down: ## para a stack (mantém volumes)
	$(COMPOSE) down

ps: ## estado e saúde dos contêineres
	$(COMPOSE) ps

logs: ## segue os logs (ex.: make logs s=trader)
	$(COMPOSE) logs -f --tail=200 $(s)

migrate: ## aplica migrações pendentes
	$(COMPOSE) run --rm migrate

test: ## testes unitários (sem Docker)
	$(BACKEND) uv run pytest -m "not integration" --cov --cov-report=term-missing:skip-covered

test-integration: ## testes com Postgres/Redis reais (sobe a stack dev)
	$(COMPOSE_DEV) up -d --wait postgres redis
	$(COMPOSE_DEV) run --rm migrate
	set -a && source ./.env && set +a && $(BACKEND) uv run pytest -m integration

lint: ## ruff
	$(BACKEND) uv run ruff check . && uv run ruff format --check .

typecheck: ## mypy --strict
	$(BACKEND) uv run mypy

check: lint typecheck test ## tudo que roda sem Docker

smoke: ## sobe a stack completa e valida saúde, isolamento de rede e autorreinício
	bash infra/scripts/smoke.sh

backup: ## dump do Postgres comprimido (e cifrado se AGE_RECIPIENT estiver definido)
	bash infra/scripts/backup_postgres.sh

check-binance: ## diagnóstico da Binance (relógio, chave, conta) — rode na VPS
	$(COMPOSE) run --rm --no-deps trader python -m quantum_one.services.check_binance

status: ## estado do scanner e da conexão com a Binance (JSON)
	@for s in marketdata trader; do echo "== $$s =="; $(COMPOSE) exec -T $$s python -m quantum_one.services.status; done

velas: ## velas de 1m gravadas na última hora, por par (esperado: 60)
	@$(COMPOSE) exec -T postgres psql -U postgres -d quantum_one -c "SELECT symbol, count(*) AS velas_ultima_hora FROM q1.candles WHERE open_time > now() - interval '1 hour' GROUP BY symbol ORDER BY symbol;"

set-binance-key: ## grava a chave Ed25519 no .env (ex.: make set-binance-key PEM=~/binance-keys/private.pem)
	python3 infra/scripts/set_binance_key.py $(PEM)
