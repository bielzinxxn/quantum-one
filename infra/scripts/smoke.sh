#!/usr/bin/env bash
# Smoke test da stack completa. Critério de aceite da Fase 2.
set -euo pipefail
cd "$(dirname "$0")/../.."

APPS=(marketdata engine trader accounting api)
pass() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFALHA\033[0m %s\n' "$1"; exit 1; }

health() { docker compose exec -T "$1" python -m quantum_one.services.healthcheck "$2"; }

wait_healthy() {  # $1 = serviço, $2 = timeout s
  local cid status
  for _ in $(seq 1 "$2"); do
    cid="$(docker compose ps -q "$1")"
    status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || true)"
    [[ "$status" == "healthy" ]] && return 0
    sleep 1
  done
  return 1
}

echo "1) subindo stack"
docker compose up -d --wait --wait-timeout 180 >/dev/null 2>&1 || fail "stack não ficou saudável"
pass "todos os contêineres healthy"

echo "2) migração"
[[ "$(docker inspect -f '{{.State.ExitCode}}' "$(docker compose ps -aq migrate)")" == "0" ]] \
  && pass "migrate terminou com código 0" || fail "migrate falhou"

echo "3) readiness (Postgres + Redis) de cada serviço"
for s in "${APPS[@]}"; do health "$s" /health/ready && pass "$s ready" || fail "$s não ready"; done

echo "4) fail-closed: trader nasce BLOQUEADO"
docker compose exec -T trader python -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('http://127.0.0.1:8080/health/ready'))
assert d['trading_state']=='BLOCKED', d
assert d['exchange']['state'] in ('credentials_missing','ok','degraded','blocked','starting'), d
print('     exchange.state =', d['exchange']['state'])" && pass "trading_state=BLOCKED + status da exchange exposto" || fail "trader não está BLOCKED"
docker compose exec -T marketdata python -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('http://127.0.0.1:8080/health/ready'))
print('     marketdata exchange.state =', d['exchange']['state'], d['exchange'].get('last_error'))
sc=d['scanner']; print('     scanner: connected =', sc['connected'], '| universo =', sc['universe'], '| erro =', sc.get('error'))" \
  && pass "marketdata expõe status da exchange e do scanner" || fail "marketdata sem status"

echo "5) API só no loopback do host"
port="$(docker compose port api 8080)"
[[ "$port" == 127.0.0.1:* ]] && pass "api publicada em $port" || fail "api exposta em $port"

echo "6) isolamento de rede: engine/accounting sem internet"
for s in engine accounting; do
  if docker compose exec -T "$s" python -c "
import socket; socket.create_connection(('1.1.1.1', 443), timeout=3)" 2>/dev/null; then
    fail "$s conseguiu sair para a internet"
  else pass "$s sem rota externa"; fi
done

echo "7) segredos: só o trader recebe BINANCE_API_*"
for s in marketdata engine accounting api; do
  docker compose exec -T "$s" sh -c 'env | grep -q "^BINANCE_API_"' && fail "$s recebeu BINANCE_API_*" || true
done
pass "BINANCE_API_* ausente fora do trader"

echo "8) contêiner roda como não-root e FS somente leitura"
for s in "${APPS[@]}"; do
  docker compose exec -T "$s" sh -c '[ "$(id -u)" != "0" ] && ! touch /app/x 2>/dev/null' \
    && pass "$s uid≠0, /app read-only" || fail "$s com privilégios indevidos"
done

echo "9) autorreinício: matar o processo do engine com SIGKILL"
docker compose exec -T engine python -c "
import os, signal
me = os.getpid()
for p in filter(str.isdigit, os.listdir('/proc')):
    p = int(p)
    if p in (1, me): continue
    try: cmd = open(f'/proc/{p}/cmdline','rb').read()
    except OSError: continue
    if b'quantum_one.services.cli' in cmd: os.kill(p, signal.SIGKILL)
" || true
sleep 3
restarts="$(docker inspect -f '{{.RestartCount}}' "$(docker compose ps -q engine)")"
[[ "$restarts" -ge 1 ]] || fail "engine não reiniciou (RestartCount=$restarts)"
wait_healthy engine 60 && pass "engine reiniciou sozinho e voltou healthy (RestartCount=$restarts)" \
  || fail "engine não voltou healthy"

echo "10) logs sem segredos"
set -a; source ./.env; set +a
logs="$(docker compose logs --no-color 2>&1)"
for v in PG_MARKETDATA_PASSWORD PG_ENGINE_PASSWORD PG_TRADER_PASSWORD PG_ACCOUNTING_PASSWORD \
         PG_API_PASSWORD PG_MIGRATOR_PASSWORD REDIS_PASSWORD POSTGRES_SUPERUSER_PASSWORD; do
  grep -qF -- "${!v}" <<<"$logs" && fail "segredo $v apareceu nos logs"
done
pass "nenhuma senha nos logs"

echo
echo "SMOKE OK"
