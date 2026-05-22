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
PG_PORT="${PG_PORT:-5432}"
PGDATA="${DATA_DIR}/pgdata"
BLOB_DIR="${DATA_DIR}/blobs"
PGPASS_FILE="${DATA_DIR}/.pgpass_tracker"
PGVERSION_FILE="${DATA_DIR}/.pgversion"

echo "=== setup-data-volume: DATA_DIR=${DATA_DIR} PGDATA=${PGDATA}"

# --- 0. the volume must actually be mounted -------------------------------
if ! mountpoint -q "$DATA_DIR" 2>/dev/null && [ ! -d "$DATA_DIR" ]; then
  echo "FATAL: ${DATA_DIR} does not exist — is the network volume mounted?" >&2
  exit 1
fi
mkdir -p "$DATA_DIR"

# --- 1. resolve + install postgres ----------------------------------------
# A cluster on disk is tied to one major version, so the version is PINNED
# on the volume (.pgversion) the first time and reused on every reattach.
# Fresh volume: prefer $PG_VERSION (default 16) via the PGDG repo; if PGDG
# is unreachable, fall back to the newest PostgreSQL in the base repos
# (PG12 on Ubuntu focal). Either way the data is durable on the volume.
export DEBIAN_FRONTEND=noninteractive
apt-get update -q || true

pg_available() { apt-cache show "postgresql-$1" >/dev/null 2>&1; }

add_pgdg() {
  echo "    adding PGDG apt repo"
  apt-get install -y -q curl ca-certificates lsb-release gnupg >/dev/null 2>&1 || true
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc 2>/dev/null || return 1
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get update -q 2>/dev/null || true
}

newest_available() {
  # Highest postgresql-NN currently installable, by apt-cache search.
  apt-cache search '^postgresql-[0-9]+$' 2>/dev/null \
    | grep -oE 'postgresql-[0-9]+' | grep -oE '[0-9]+$' | sort -n | tail -1
}

if [ -s "$PGVERSION_FILE" ]; then
  PG_VERSION="$(cat "$PGVERSION_FILE")"
  echo "    volume pins PostgreSQL ${PG_VERSION} (reattach)"
else
  PG_VERSION="${PG_VERSION:-16}"
fi

PGBIN="/usr/lib/postgresql/${PG_VERSION}/bin"
if [ ! -x "${PGBIN}/initdb" ]; then
  if ! pg_available "$PG_VERSION"; then
    add_pgdg || true
  fi
  if ! pg_available "$PG_VERSION"; then
    fallback="$(newest_available)"
    if [ -n "$fallback" ]; then
      echo "    postgresql-${PG_VERSION} unavailable; falling back to postgresql-${fallback}"
      PG_VERSION="$fallback"
      PGBIN="/usr/lib/postgresql/${PG_VERSION}/bin"
    fi
  fi
  echo "=== installing postgresql-${PG_VERSION}"
  apt-get install -y -q "postgresql-${PG_VERSION}" "postgresql-client-${PG_VERSION}"
fi
[ -x "${PGBIN}/initdb" ] || { echo "FATAL: no usable postgresql install (${PGBIN})" >&2; exit 1; }

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
  # Pin the major version on the volume so every future reattach installs
  # the matching binary (a cluster can't be opened by a different major).
  printf '%s' "$PG_VERSION" > "$PGVERSION_FILE"
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
