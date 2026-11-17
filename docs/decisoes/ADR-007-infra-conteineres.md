# ADR-007 — Infraestrutura de contêineres

**Status:** aceita (2026-11-17, Fase 2)

**Decisões:**
1. **Imagem única de backend.** Cada serviço é um `command` diferente da mesma imagem, com Python 3.12 e dependências fixadas no `uv.lock`. As imagens base são fixadas por digest.
2. **Três redes.**
   - `internal` não tem saída para a internet: Postgres, Redis, `engine`, `accounting`, `migrate`.
   - `egress` dá internet só ao `marketdata` e ao `trader`.
   - `edge` só existe para publicar a API em `127.0.0.1`.
3. **Segredos por serviço,** sem `env_file` global. A chave da Binance só existe no `trader`.
4. **Um papel de Postgres por serviço** (`q1_*`) e schema `q1`, cujo dono é o `q1_migrator`. A API tem `default_transaction_read_only=on`; quando precisar escrever (auditoria), terá de pedir isso explicitamente na transação. `audit_log` é append-only por trigger, válido até para o dono do schema.
5. **Saúde.** `/health/live` mostra se o loop está batendo e é o que o HEALTHCHECK do Docker usa. `/health/ready` mostra se Postgres e Redis estão OK.
6. **Autorreinício.** O Docker não reinicia contêiner que está só *unhealthy*. Por isso há um **watchdog em thread** que encerra o processo (código 70) se o event loop parar por mais de `WATCHDOG_TIMEOUT_S`, e o `restart: unless-stopped` sobe o processo de novo. Falha de configuração sai com código 78.
7. **Contêineres endurecidos:** `read_only`, `cap_drop: ALL`, `no-new-privileges`, usuário uid 10001 e rotação de logs (10 MB × 5).
8. **Redis:** AOF ligado, `noeviction`, FLUSHALL, FLUSHDB, CONFIG, KEYS, DEBUG e SHUTDOWN desabilitados, senha obrigatória.

**Consequências:**
- Com a stack completa, o consumo fica em torno de 1–1,5 GB de RAM em repouso.
- Trocar uma senha do Postgres depois da instalação exige `ALTER ROLE` manual (ver `infra/vps/SETUP.md`).
- Atualizar uma imagem base é um ato deliberado: trocar o digest e rodar o smoke test.
