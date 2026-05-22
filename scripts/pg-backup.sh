#!/usr/bin/env bash
# Snapshot the local tracker DB to the network volume (durability).
#
# PostgreSQL runs on the pod's LOCAL disk (MooseFS can't host a PG data dir
# — see setup-data-volume.sh). These pg_dump snapshots on the volume are
# what survives a pod/host death; a fresh pod restores the newest one.
#
# Run by cron (every 30 min, installed by setup-data-volume.sh) and by
# deploy.sh after each alembic upgrade. Idempotent; keeps the last N.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
PG_PORT="${PG_PORT:-5432}"
DUMP_DIR="${DATA_DIR}/pgdumps"
KEEP="${KEEP:-48}"   # ~24h at 30-min cadence

newest_pg() {
  ls -d /usr/lib/postgresql/*/bin 2>/dev/null \
    | grep -oE '/[0-9]+/' | tr -d / | sort -n | tail -1
}
PGBIN="/usr/lib/postgresql/$(newest_pg)/bin"
mkdir -p "$DUMP_DIR"

# Skip cleanly if postgres isn't up or the db is absent.
if ! su postgres -c "${PGBIN}/psql -p ${PG_PORT} -tAc \"SELECT 1 FROM pg_database WHERE datname='tracker'\"" 2>/dev/null | grep -q 1; then
  echo "$(date -u +%FT%TZ) pg-backup: tracker db not available, skipping"
  exit 0
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
tmp="${DUMP_DIR}/.tracker-${ts}.sql.gz.partial"
final="${DUMP_DIR}/tracker-${ts}.sql.gz"

# --no-owner/--no-privileges so a restore into a fresh cluster (where the
# tracker role is created separately) doesn't choke on ownership grants.
su postgres -c "${PGBIN}/pg_dump -p ${PG_PORT} --no-owner --no-privileges tracker" \
  | gzip > "$tmp"
mv "$tmp" "$final"
echo "$(date -u +%FT%TZ) pg-backup: wrote ${final} ($(du -h "$final" | cut -f1))"

# Retention: keep newest $KEEP.
ls -1t "${DUMP_DIR}"/tracker-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
