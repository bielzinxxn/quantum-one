#!/usr/bin/env bash
# Backup lógico do Postgres: pg_dump (formato custom, já comprimido) dentro do contêiner.
# Se AGE_RECIPIENT estiver definido (chave pública age), o arquivo sai cifrado.
# Copie o resultado para FORA da VPS (ex.: rclone para storage externo).
set -euo pipefail

cd "$(dirname "$0")/../.."
OUT_DIR="${BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB="${POSTGRES_DB:-quantum_one}"
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
umask 077

FILE="$OUT_DIR/quantum_one_${STAMP}.dump"
docker compose exec -T postgres pg_dump -U postgres -d "$DB" --format=custom --no-owner > "$FILE"

# valida que o dump é legível antes de considerá-lo um backup
docker compose exec -T postgres pg_restore --list < "$FILE" > /dev/null

if [[ -n "${AGE_RECIPIENT:-}" ]]; then
  age -r "$AGE_RECIPIENT" -o "$FILE.age" "$FILE"
  rm -f "$FILE"
  FILE="$FILE.age"
fi

# retenção local
find "$OUT_DIR" -name 'quantum_one_*' -mtime +"${BACKUP_RETENTION_DAYS:-14}" -delete
echo "backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
