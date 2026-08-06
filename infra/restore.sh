#!/usr/bin/env bash
#
# ScholarHUB database restore script.
#
# Usage:
#   ./restore.sh <backup-file.gz> [--db-url URL]
#
# Defaults:
#   --db-url  postgresql://scholarhub:scholarhub_dev@localhost:5432/scholarhub
#
# Behaviour:
#   - Validates the backup file exists and is a gzip file.
#   - Drops and recreates the public schema, then restores via pg_restore.
#   - Logs to stdout with [YYYY-MM-DD HH:MM:SS] timestamps.

set -euo pipefail

# --- defaults -----------------------------------------------------------
DB_URL="postgresql://scholarhub:scholarhub_dev@localhost:5432/scholarhub"

# --- helpers ------------------------------------------------------------
log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

# --- parse args ---------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup-file.gz> [--db-url URL]"
  echo ""
  echo "  backup-file.gz  Path to a gzip-compressed pg_dump custom-format backup"
  echo "  --db-url URL    Target PostgreSQL connection URL"
  exit 1
fi

BACKUP_FILE="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-url)
      DB_URL="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 <backup-file.gz> [--db-url URL]"
      echo ""
      echo "  backup-file.gz  Path to a gzip-compressed pg_dump custom-format backup"
      echo "  --db-url URL    Target PostgreSQL connection URL (default: postgresql://scholarhub:scholarhub_dev@localhost:5432/scholarhub)"
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

# --- pre-flight checks --------------------------------------------------
command -v pg_restore >/dev/null 2>&1 || die "pg_restore not found — install PostgreSQL client tools"
command -v psql       >/dev/null 2>&1 || die "psql not found — install PostgreSQL client tools"
command -v gzip       >/dev/null 2>&1 || die "gzip not found"

if [[ ! -f "$BACKUP_FILE" ]]; then
  die "Backup file not found: ${BACKUP_FILE}"
fi

if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
  die "File is not a valid gzip archive: ${BACKUP_FILE}"
fi

# --- restore ------------------------------------------------------------
log "Starting restore from ${BACKUP_FILE} → ${DB_URL}"

log "Dropping and recreating public schema…"
psql "$DB_URL" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" 2>&1 \
  || die "Failed to reset public schema"

log "Restoring database…"
gunzip -c "$BACKUP_FILE" | pg_restore --dbname="$DB_URL" --clean --if-exists --no-owner --no-acl --single-transaction 2>&1

if [[ ${PIPESTATUS[0]} -ne 0 || ${PIPESTATUS[1]} -ne 0 ]]; then
  die "pg_restore failed — restore may be incomplete"
fi

log "Restore complete"