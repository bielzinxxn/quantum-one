#!/bin/sh
# Executado UMA VEZ pelo entrypoint oficial do Postgres, só com volume vazio.
# Cria o schema q1, o papel migrador (dono do schema) e um papel por serviço.
# Senhas vêm de variáveis de ambiente e entram como variáveis psql (:'pw'),
# nunca interpoladas no SQL pelo shell.
set -eu

: "${POSTGRES_DB:?}" "${PG_MIGRATOR_PASSWORD:?}" "${PG_MARKETDATA_PASSWORD:?}" \
  "${PG_ENGINE_PASSWORD:?}" "${PG_TRADER_PASSWORD:?}" "${PG_ACCOUNTING_PASSWORD:?}" \
  "${PG_API_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v db="$POSTGRES_DB" \
  -v pw_migrator="$PG_MIGRATOR_PASSWORD" \
  -v pw_marketdata="$PG_MARKETDATA_PASSWORD" \
  -v pw_engine="$PG_ENGINE_PASSWORD" \
  -v pw_trader="$PG_TRADER_PASSWORD" \
  -v pw_accounting="$PG_ACCOUNTING_PASSWORD" \
  -v pw_api="$PG_API_PASSWORD" <<'EOSQL'
-- ninguém cria objetos no schema public
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;

CREATE ROLE q1_migrator   LOGIN PASSWORD :'pw_migrator';
CREATE ROLE q1_marketdata LOGIN PASSWORD :'pw_marketdata';
CREATE ROLE q1_engine     LOGIN PASSWORD :'pw_engine';
CREATE ROLE q1_trader     LOGIN PASSWORD :'pw_trader';
CREATE ROLE q1_accounting LOGIN PASSWORD :'pw_accounting';
CREATE ROLE q1_api        LOGIN PASSWORD :'pw_api';

CREATE SCHEMA q1 AUTHORIZATION q1_migrator;

GRANT CONNECT ON DATABASE :"db"
  TO q1_migrator, q1_marketdata, q1_engine, q1_trader, q1_accounting, q1_api;
GRANT USAGE ON SCHEMA q1 TO q1_marketdata, q1_engine, q1_trader, q1_accounting, q1_api;

ALTER ROLE q1_migrator   SET search_path = q1;
ALTER ROLE q1_marketdata SET search_path = q1;
ALTER ROLE q1_engine     SET search_path = q1;
ALTER ROLE q1_trader     SET search_path = q1;
ALTER ROLE q1_accounting SET search_path = q1;
ALTER ROLE q1_api        SET search_path = q1;

-- a API é somente leitura por padrão; permissões finas de escrita vêm nas migrações
ALTER ROLE q1_api SET default_transaction_read_only = on;
EOSQL
