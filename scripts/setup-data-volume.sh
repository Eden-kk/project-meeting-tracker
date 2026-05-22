#!/usr/bin/env bash
# Durable storage on RunPod — runs ON the app pod.
#
# RunPod network volumes are MooseFS (FUSE). The mount reports mode 0777 to
# every NON-root user regardless of the real mode, so PostgreSQL — which
# runs as the `postgres` user and refuses a data dir that isn't 0700/0750 —
# cannot keep its data directory on the volume (it always sees 0777 and
# dies with "data directory has invalid permissions"). Proven on this pod:
# root sees 0700, postgres sees 0777 for the same dir. (This is almost
# certainly why the old 2-pod design quietly fell back to a local Postgres.)
#
# So durability is split:
#   - BLOBS live directly on the volume (/data/blobs). The app runs as root,
#     so the 0777 view is harmless and audio survives any pod/host death.
#   - POSTGRES runs on LOCAL container disk (correct perms, fast) and is made
#     durable by frequent pg_dump snapshots written to the volume
#     (/data/pgdumps). A fresh pod auto-restores from the newest snapshot.
#     A cron keeps snapshots flowing; deploy.sh also snapshots after migrate.
#
# Idempotent. Env:
#   DATA_DIR     volume mount (default /data)
#   PG_PASSWORD  tracker role password (first init; else read from volume)
#   PG_PORT      postgres port (default 5432)
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
PG_PORT="${PG_PORT:-5432}"
BLOB_DIR="${DATA_DIR}/blobs"
DUMP_DIR="${DATA_DIR}/pgdumps"
PGPASS_FILE="${DATA_DIR}/.pgpass_tracker"
LOCAL_PGDATA="${LOCAL_PGDATA:-/var/lib/pgdata-local}"

echo "=== setup-data-volume: DATA_DIR=${DATA_DIR} LOCAL_PGDATA=${LOCAL_PGDATA}"

# --- 0. volume mounted? ---------------------------------------------------
if ! mountpoint -q "$DATA_DIR" 2>/dev/null && [ ! -d "$DATA_DIR" ]; then
  echo "FATAL: ${DATA_DIR} does not exist — is the network volume mounted?" >&2
  exit 1
fi
mkdir -p "$DATA_DIR" "$BLOB_DIR" "$DUMP_DIR"

# --- 1. install postgres (local) ------------------------------------------
export DEBIAN_FRONTEND=noninteractive
newest_pg() {
  ls -d /usr/lib/postgresql/*/bin 2>/dev/null \
    | grep -oE '/[0-9]+/' | tr -d / | sort -n | tail -1
}
PG_VERSION="$(newest_pg || true)"
if [ -z "$PG_VERSION" ]; then
  echo "=== installing postgresql"
  apt-get update -q || true
  cand="$(apt-cache search '^postgresql-[0-9]+$' 2>/dev/null | grep -oE 'postgresql-[0-9]+' | grep -oE '[0-9]+$' | sort -n | tail -1)"
  cand="${cand:-12}"
  apt-get install -y -q "postgresql-${cand}" "postgresql-client-${cand}"
  PG_VERSION="$(newest_pg)"
fi
PGBIN="/usr/lib/postgresql/${PG_VERSION}/bin"
[ -x "${PGBIN}/initdb" ] || { echo "FATAL: no postgres install at ${PGBIN}" >&2; exit 1; }
echo "    using PostgreSQL ${PG_VERSION}"

# --- 2. resolve password (provided wins; else stored on volume) -----------
if [ -n "${PG_PASSWORD:-}" ]; then
  :
elif [ -f "$PGPASS_FILE" ]; then
  PG_PASSWORD="$(cat "$PGPASS_FILE")"
else
  echo "FATAL: no PG_PASSWORD provided and ${PGPASS_FILE} absent" >&2
  exit 1
fi

# --- 3. local cluster: init if absent -------------------------------------
FRESH_CLUSTER=0
if [ ! -s "${LOCAL_PGDATA}/PG_VERSION" ]; then
  echo "=== initdb local cluster at ${LOCAL_PGDATA}"
  rm -rf "$LOCAL_PGDATA"
  install -d -o postgres -g postgres -m 700 "$(dirname "$LOCAL_PGDATA")" 2>/dev/null || true
  install -d -o postgres -g postgres -m 700 "$LOCAL_PGDATA"
  su postgres -c "${PGBIN}/initdb -D '${LOCAL_PGDATA}' --encoding=UTF8 --locale=C.UTF-8"
  {
    echo "listen_addresses = '127.0.0.1'"
    echo "port = ${PG_PORT}"
  } >> "${LOCAL_PGDATA}/postgresql.conf"
  echo "host all all 127.0.0.1/32 scram-sha-256" >> "${LOCAL_PGDATA}/pg_hba.conf"
  FRESH_CLUSTER=1
fi

# --- 4. start postgres ----------------------------------------------------
if su postgres -c "${PGBIN}/pg_ctl -D '${LOCAL_PGDATA}' status" >/dev/null 2>&1; then
  echo "=== postgres already running"
else
  echo "=== starting postgres"
  su postgres -c "${PGBIN}/pg_ctl -D '${LOCAL_PGDATA}' -l '/var/log/pg-local.log' -w start"
fi

psql_su() { su postgres -c "${PGBIN}/psql -p ${PG_PORT} $*"; }

# --- 5. role + db + sync password -----------------------------------------
echo "=== ensuring tracker role + database"
if psql_su "-tAc \"SELECT 1 FROM pg_roles WHERE rolname='tracker'\"" | grep -q 1; then
  psql_su "-v ON_ERROR_STOP=1 -c \"ALTER ROLE tracker LOGIN PASSWORD '${PG_PASSWORD}'\""
else
  psql_su "-v ON_ERROR_STOP=1 -c \"CREATE ROLE tracker LOGIN PASSWORD '${PG_PASSWORD}'\""
fi
if ! psql_su "-tAc \"SELECT 1 FROM pg_database WHERE datname='tracker'\"" | grep -q 1; then
  su postgres -c "${PGBIN}/createdb -p ${PG_PORT} -O tracker tracker"
fi
umask 077; printf '%s' "$PG_PASSWORD" > "$PGPASS_FILE"; chmod 600 "$PGPASS_FILE"

# --- 6. restore from newest volume snapshot if the DB is empty ------------
# "Empty" = no `meetings` table yet. A fresh local cluster on a recreated
# pod restores the last snapshot taken before the previous pod died.
has_schema="$(psql_su "-tAd tracker -c \"SELECT to_regclass('public.meetings') IS NOT NULL\"" | tr -d '[:space:]')"
if [ "$has_schema" != "t" ]; then
  latest="$(ls -1t "${DUMP_DIR}"/tracker-*.sql.gz 2>/dev/null | head -1 || true)"
  if [ -n "$latest" ]; then
    echo "=== restoring tracker DB from snapshot: ${latest}"
    gunzip -c "$latest" | su postgres -c "${PGBIN}/psql -p ${PG_PORT} -q -d tracker" \
      && echo "    restore OK" || echo "    WARN: restore reported errors (continuing)"
  else
    echo "=== no snapshot to restore (fresh database)"
  fi
fi

# --- 7. install the backup cron (snapshots -> volume) ---------------------
# Hourly + retained; deploy.sh also snapshots after each migrate.
if [ -x scripts/pg-backup.sh ]; then
  CRON_LINE="*/30 * * * * cd $(pwd) && DATA_DIR=${DATA_DIR} PG_PORT=${PG_PORT} bash scripts/pg-backup.sh >> /var/log/pg-backup.log 2>&1"
  ( crontab -l 2>/dev/null | grep -v 'pg-backup.sh' ; echo "$CRON_LINE" ) | crontab - 2>/dev/null \
    && service cron start >/dev/null 2>&1 || true
  echo "=== backup cron installed (*/30 min -> ${DUMP_DIR})"
fi

echo "=== setup-data-volume OK"
echo "    DATABASE_URL=postgresql+psycopg://tracker:<pw>@127.0.0.1:${PG_PORT}/tracker"
echo "    BLOB_STORE_DIR=${BLOB_DIR}   snapshots=${DUMP_DIR}"
