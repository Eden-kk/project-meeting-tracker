#!/usr/bin/env bash
# Durable storage setup — runs ON the app pod.
#
# Puts BOTH the Postgres data directory and the blob store on the network
# volume mounted at $DATA_DIR (default /data), so the data survives any
# pod/host death. Provision a replacement pod, attach the SAME volume,
# re-run this script, and the database + audio blobs are exactly where you
# left them.
#
# This is the fix for the recurring "host OOM -> can't resume -> data lost"
# failure: with no network volume the DB lived on the pod's ephemeral
# container disk and every host outage destroyed it. See docs/pod-deployment.md.
#
# Idempotent:
#   - if $PGDATA already has a cluster (volume re-attached), just start it
#   - else initdb a fresh cluster, create the tracker role + db
#   - blob dir is created if missing
#
# Env (all optional, sane defaults):
#   DATA_DIR      volume mount path        (default /data)
#   PG_VERSION    postgres major version   (default 16)
#   PG_PASSWORD   tracker role password    (REQUIRED on first init; read
#                                           from /data/.pgpass after that)
#   PG_PORT       postgres port            (default 5432)
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
PG_VERSION="${PG_VERSION:-16}"
PG_PORT="${PG_PORT:-5432}"
PGDATA="${DATA_DIR}/pgdata"
BLOB_DIR="${DATA_DIR}/blobs"
PGBIN="/usr/lib/postgresql/${PG_VERSION}/bin"
PGPASS_FILE="${DATA_DIR}/.pgpass_tracker"

echo "=== setup-data-volume: DATA_DIR=${DATA_DIR} PGDATA=${PGDATA}"

# --- 0. the volume must actually be mounted -------------------------------
if ! mountpoint -q "$DATA_DIR" 2>/dev/null && [ ! -d "$DATA_DIR" ]; then
  echo "FATAL: ${DATA_DIR} does not exist — is the network volume mounted?" >&2
  exit 1
fi
mkdir -p "$DATA_DIR"

# --- 1. install postgres server if absent ---------------------------------
if [ ! -x "${PGBIN}/initdb" ]; then
  echo "=== installing postgresql-${PG_VERSION}"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q "postgresql-${PG_VERSION}" "postgresql-client-${PG_VERSION}"
fi

# --- 2. resolve the password ----------------------------------------------
# .env.local / DATABASE_URL is the source of truth for the app, so a
# provided PG_PASSWORD WINS — step 5 syncs the role to it (self-healing for
# the volume-reuse case, where a new pod brings a new password). Only when
# none is provided (e.g. a bare redeploy that didn't source .env.local) do
# we fall back to the password stored on the volume.
if [ -n "${PG_PASSWORD:-}" ]; then
  : # use provided (authoritative)
elif [ -f "$PGPASS_FILE" ]; then
  PG_PASSWORD="$(cat "$PGPASS_FILE")"
else
  echo "FATAL: no PG_PASSWORD provided and ${PGPASS_FILE} absent" >&2
  exit 1
fi

chown -R postgres:postgres "$DATA_DIR" 2>/dev/null || true

# --- 3. init the cluster if the volume is fresh ---------------------------
FRESH_INIT=0
if [ ! -s "${PGDATA}/PG_VERSION" ]; then
  echo "=== initdb fresh cluster at ${PGDATA}"
  mkdir -p "$PGDATA"
  chown -R postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"
  su postgres -c "${PGBIN}/initdb -D '${PGDATA}' --encoding=UTF8 --locale=C.UTF-8"
  FRESH_INIT=1
  # Listen on localhost only; the app talks to it over 127.0.0.1.
  {
    echo "listen_addresses = '127.0.0.1'"
    echo "port = ${PG_PORT}"
  } >> "${PGDATA}/postgresql.conf"
  echo "host all all 127.0.0.1/32 scram-sha-256" >> "${PGDATA}/pg_hba.conf"
else
  echo "=== existing cluster found at ${PGDATA} — reusing (data preserved)"
fi

# --- 4. start postgres -----------------------------------------------------
if su postgres -c "${PGBIN}/pg_ctl -D '${PGDATA}' status" >/dev/null 2>&1; then
  echo "=== postgres already running"
else
  echo "=== starting postgres"
  su postgres -c "${PGBIN}/pg_ctl -D '${PGDATA}' -l '${DATA_DIR}/pg.log' -w start"
fi

# --- 5. ensure role + db + sync password (idempotent, every run) -----------
# Runs on every invocation, not just fresh init, so a re-attached volume on
# a new pod has its role password synced to the new .env.local value (the
# app's DATABASE_URL must match). PG_PASSWORD is auto-generated hex
# (openssl rand -hex), so single-quoting in SQL is safe. We avoid PL/pgSQL
# dollar-quoting (fragile through `su -c "..."`) by guarding with a SELECT.
echo "=== ensuring tracker role + database (password synced to env)"
if su postgres -c "${PGBIN}/psql -p ${PG_PORT} -tAc \"SELECT 1 FROM pg_roles WHERE rolname='tracker'\"" | grep -q 1; then
  su postgres -c "${PGBIN}/psql -p ${PG_PORT} -v ON_ERROR_STOP=1 -c \"ALTER ROLE tracker LOGIN PASSWORD '${PG_PASSWORD}'\""
else
  su postgres -c "${PGBIN}/psql -p ${PG_PORT} -v ON_ERROR_STOP=1 -c \"CREATE ROLE tracker LOGIN PASSWORD '${PG_PASSWORD}'\""
fi
if ! su postgres -c "${PGBIN}/psql -p ${PG_PORT} -tAc \"SELECT 1 FROM pg_database WHERE datname='tracker'\"" | grep -q 1; then
  su postgres -c "${PGBIN}/createdb -p ${PG_PORT} -O tracker tracker"
fi
umask 077
printf '%s' "$PG_PASSWORD" > "$PGPASS_FILE"
chmod 600 "$PGPASS_FILE"
echo "    role/db ready; password stored at ${PGPASS_FILE}"

# --- 6. blob dir on the volume --------------------------------------------
mkdir -p "$BLOB_DIR"
echo "=== blob dir ready at ${BLOB_DIR}"

echo "=== setup-data-volume OK"
echo "    DATABASE_URL=postgresql+psycopg://tracker:<pw>@127.0.0.1:${PG_PORT}/tracker"
echo "    BLOB_STORE_DIR=${BLOB_DIR}"
