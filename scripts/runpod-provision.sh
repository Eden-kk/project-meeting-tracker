#!/usr/bin/env bash
# Provision a 2-pod RunPod topology for project-meeting-tracker:
#
#   db-pod   :  postgres:16 + network volume (data survives pod death)
#   app-pod  :  ubuntu:22.04, bootstrapped to run storage-router + SPA
#
# Why 2 pods (not 1): the 2026-05-15 incident — paused app pod couldn't
# resume due to host RAM exhaustion, and the DB was on the same pod, so
# the data was held hostage with the app. Splitting DB onto its own pod
# with a network volume means an app-pod outage no longer endangers the
# database. The handbook covers this in §6 / Issue #7.
#
# Reads from .env.local (gitignored):
#   RUNPOD_API_KEY      required
#   RUNPOD_DC           optional, default US-OR-1
#   PG_PASSWORD         optional, auto-generated if absent
#
# Writes to .env.local on success:
#   RUNPOD_APP_POD_ID, RUNPOD_DB_POD_ID, RUNPOD_DB_VOLUME_ID
#   APP_POD_SSH_HOST, APP_POD_SSH_PORT
#   DB_POD_HOST, DB_POD_PORT
#   DATABASE_URL (pointed at db-pod's exposed PG)
#   PG_PASSWORD (if generated here)
#
# After this script returns, run `bash scripts/bootstrap-app-pod.sh`
# from this machine — it SSHes into the new app pod and runs the
# install + first deploy.
#
# Docs: https://rest.runpod.io/v1/docs

set -euo pipefail

API='https://rest.runpod.io/v1'
ENV_FILE="${ENV_FILE:-.env.local}"

[ -f "$ENV_FILE" ] && { set -a; . "./${ENV_FILE}"; set +a; }
: "${RUNPOD_API_KEY:?missing RUNPOD_API_KEY (in .env.local or env)}"
DC="${RUNPOD_DC:-US-OR-1}"
PG_PASSWORD="${PG_PASSWORD:-$(openssl rand -hex 16)}"

# Pubkey to bake into both pods. Use this machine's key (which the user
# explicitly authorized).
PUBKEY_PATH="${PUBKEY_PATH:-$HOME/.ssh/id_ed25519.pub}"
PUBKEY="$(cat "$PUBKEY_PATH")"

api() {
  # $1=method  $2=path  $3=json body (optional)
  if [ -n "${3:-}" ]; then
    curl -sS -X "$1" -H "Authorization: Bearer $RUNPOD_API_KEY" \
      -H 'Content-Type: application/json' -d "$3" "${API}$2"
  else
    curl -sS -X "$1" -H "Authorization: Bearer $RUNPOD_API_KEY" "${API}$2"
  fi
}

j() { python3 -c "import json,sys; d=json.load(sys.stdin); $1" 2>/dev/null || echo "" ; }

echo "=== [1/6] create network volume (50 GB, dc=${DC}) for db-pod"
vol_resp=$(api POST /networkvolumes "{\"name\":\"tracker-db-vol\",\"size\":50,\"dataCenterId\":\"${DC}\"}")
echo "    $vol_resp"
VOLUME_ID=$(echo "$vol_resp" | j 'print(d.get("id",""))')
[ -n "$VOLUME_ID" ] || { echo "FAILED: no volume id"; exit 1; }
echo "    volume id: $VOLUME_ID"

echo "=== [2/6] create db-pod (postgres:16, vol attached, cpu)"
# postgres:16 image listens on 5432; PUBLIC_KEY env is consumed by the
# RunPod base image's ssh entrypoint — but plain postgres:16 doesn't run
# sshd, so for DB we expose 5432 directly (no ssh needed; we drive PG
# via the app pod or via DATABASE_URL).
db_body=$(cat <<JSON
{
  "name": "tracker-db",
  "cloudType": "SECURE",
  "computeType": "CPU",
  "imageName": "postgres:16",
  "vcpuCount": 2,
  "containerDiskInGb": 10,
  "networkVolumeId": "${VOLUME_ID}",
  "volumeMountPath": "/var/lib/postgresql/data",
  "ports": ["5432/tcp"],
  "supportPublicIp": true,
  "env": {
    "POSTGRES_USER": "tracker",
    "POSTGRES_DB": "tracker",
    "POSTGRES_PASSWORD": "${PG_PASSWORD}",
    "PGDATA": "/var/lib/postgresql/data/pgdata"
  },
  "dataCenterIds": ["${DC}"]
}
JSON
)
db_resp=$(api POST /pods "$db_body")
echo "    $db_resp"
DB_POD_ID=$(echo "$db_resp" | j 'print(d.get("id",""))')
[ -n "$DB_POD_ID" ] || { echo "FAILED: no db-pod id"; exit 1; }
echo "    db-pod id: $DB_POD_ID"

echo "=== [3/6] create app-pod (ubuntu:22.04, ssh + 8050)"
# Bake the pubkey via PUBLIC_KEY env (RunPod's base ssh container reads
# this on first boot). For plain ubuntu:22.04 we install ssh ourselves
# via bootstrap-app-pod.sh — but ports are exposed at create-time.
app_body=$(cat <<JSON
{
  "name": "tracker-app",
  "cloudType": "SECURE",
  "computeType": "CPU",
  "imageName": "runpod/base:0.6.2-cpu",
  "vcpuCount": 4,
  "containerDiskInGb": 30,
  "ports": ["8050/http", "22/tcp"],
  "supportPublicIp": true,
  "env": {
    "PUBLIC_KEY": "${PUBKEY}"
  },
  "dataCenterIds": ["${DC}"]
}
JSON
)
app_resp=$(api POST /pods "$app_body")
echo "    $app_resp"
APP_POD_ID=$(echo "$app_resp" | j 'print(d.get("id",""))')
[ -n "$APP_POD_ID" ] || { echo "FAILED: no app-pod id"; exit 1; }
echo "    app-pod id: $APP_POD_ID"

echo "=== [4/6] wait for both pods RUNNING (up to 4 min)"
wait_running() {
  local id=$1 name=$2
  for i in $(seq 1 48); do
    s=$(api GET "/pods/$id" | j 'print(d.get("desiredStatus") or d.get("status") or "?")')
    echo "  +$((i*5))s  $name: $s"
    if [ "$s" = "RUNNING" ]; then return 0; fi
    sleep 5
  done
  echo "FAILED: $name not RUNNING after 4min"; return 1
}
wait_running "$DB_POD_ID" "db-pod"
wait_running "$APP_POD_ID" "app-pod"

echo "=== [5/6] resolve public endpoints from /pods/{id}"
DB_INFO=$(api GET "/pods/$DB_POD_ID")
APP_INFO=$(api GET "/pods/$APP_POD_ID")
# Port mappings live under runtime.ports[]. Each entry has privatePort,
# publicPort, ip, isIpPublic, type.
resolve() {
  # $1=json $2=privatePort
  echo "$1" | python3 -c "
import json,sys
d = json.load(sys.stdin)
for p in (d.get('runtime') or {}).get('ports') or []:
    if int(p.get('privatePort',0)) == int($2):
        print(f\"{p.get('ip','')} {p.get('publicPort','')}\"); break
"
}
read DB_HOST DB_PORT <<<"$(resolve "$DB_INFO" 5432)"
read APP_SSH_HOST APP_SSH_PORT <<<"$(resolve "$APP_INFO" 22)"
echo "    db-pod  PG  -> $DB_HOST:$DB_PORT"
echo "    app-pod SSH -> $APP_SSH_HOST:$APP_SSH_PORT"
[ -n "$DB_HOST" ] && [ -n "$APP_SSH_HOST" ] || { echo "FAILED: missing endpoints"; exit 1; }

echo "=== [6/6] persist to ${ENV_FILE}"
{
  # Drop any prior provision entries
  grep -vE '^(RUNPOD_(APP_POD_ID|DB_POD_ID|DB_VOLUME_ID)|APP_POD_SSH_(HOST|PORT)|DB_POD_(HOST|PORT)|DATABASE_URL|PG_PASSWORD)=' "$ENV_FILE" 2>/dev/null || true
  echo ""
  echo "# Added by scripts/runpod-provision.sh on $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "RUNPOD_APP_POD_ID=${APP_POD_ID}"
  echo "RUNPOD_DB_POD_ID=${DB_POD_ID}"
  echo "RUNPOD_DB_VOLUME_ID=${VOLUME_ID}"
  echo "APP_POD_SSH_HOST=${APP_SSH_HOST}"
  echo "APP_POD_SSH_PORT=${APP_SSH_PORT}"
  echo "DB_POD_HOST=${DB_HOST}"
  echo "DB_POD_PORT=${DB_PORT}"
  echo "PG_PASSWORD=${PG_PASSWORD}"
  echo "DATABASE_URL=postgresql+psycopg://tracker:${PG_PASSWORD}@${DB_HOST}:${DB_PORT}/tracker"
} > "${ENV_FILE}.new"
mv "${ENV_FILE}.new" "$ENV_FILE"
chmod 600 "$ENV_FILE"

cat <<EOF

=== provision OK
  app pod id  : $APP_POD_ID    (proxy URL: https://${APP_POD_ID}-8050.proxy.runpod.net)
  db  pod id  : $DB_POD_ID
  volume id   : $VOLUME_ID
  app SSH     : ssh -p ${APP_SSH_PORT} -i ~/.ssh/id_ed25519 root@${APP_SSH_HOST}
  DB endpoint : ${DB_HOST}:${DB_PORT}

next: bash scripts/bootstrap-app-pod.sh
EOF
