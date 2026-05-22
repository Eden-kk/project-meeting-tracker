#!/usr/bin/env bash
# Provision a durable single-pod RunPod deployment for project-meeting-tracker:
#
#   app-pod  :  runpod/base CPU pod + a NETWORK VOLUME mounted at /data.
#               Postgres data dir (/data/pgdata) AND the blob store
#               (/data/blobs) live on the volume, so the database + audio
#               survive any pod/host death.
#
# Why this shape (history): earlier setups put Postgres + blobs on the pod's
# EPHEMERAL container disk. RunPod hosts are oversubscribed; when the pod was
# stopped, the host filled up and "start pod: not enough free memory on the
# host" made it impossible to resume — and every recreate lost ALL data.
# A pod with no volume is also pinned to one host. With the data on a network
# volume, a dead/full host costs nothing: provision a fresh pod, attach the
# SAME volume, re-run bootstrap, and the data is exactly where it was.
#
# The earlier 2-pod design (separate postgres pod on a volume) drifted in
# practice — the db-pod got torn down and the app silently fell back to a
# local ephemeral Postgres. One pod with the data on its own volume removes
# that failure mode entirely.
#
# Reads from .env.local (gitignored):
#   RUNPOD_API_KEY      required
#   RUNPOD_DC           optional, default US-CA-2
#   PG_PASSWORD         optional, auto-generated if absent
#   RUNPOD_DB_VOLUME_ID optional — reuse an existing volume (data preserved)
#
# Writes to .env.local on success:
#   RUNPOD_APP_POD_ID, RUNPOD_DB_VOLUME_ID
#   APP_POD_SSH_HOST, APP_POD_SSH_PORT
#   DATABASE_URL (local: 127.0.0.1:5432), BLOB_STORE_DIR (/data/blobs)
#   PG_PASSWORD (if generated here)
#
# After this returns, run `bash scripts/bootstrap-app-pod.sh` — it SSHes in,
# mounts/initialises Postgres + blobs on the volume, and deploys.
#
# Docs: https://rest.runpod.io/v1/docs

set -euo pipefail

API='https://rest.runpod.io/v1'
ENV_FILE="${ENV_FILE:-.env.local}"

[ -f "$ENV_FILE" ] && { set -a; . "./${ENV_FILE}"; set +a; }
: "${RUNPOD_API_KEY:?missing RUNPOD_API_KEY (in .env.local or env)}"
DC="${RUNPOD_DC:-US-CA-2}"
PG_PASSWORD="${PG_PASSWORD:-$(openssl rand -hex 16)}"
DATA_MOUNT="/data"
VOLUME_SIZE_GB="${VOLUME_SIZE_GB:-50}"

PUBKEY_PATH="${PUBKEY_PATH:-$HOME/.ssh/id_ed25519.pub}"
PUBKEY="$(cat "$PUBKEY_PATH")"

api() {
  if [ -n "${3:-}" ]; then
    curl -sS -X "$1" -H "Authorization: Bearer $RUNPOD_API_KEY" \
      -H 'Content-Type: application/json' -d "$3" "${API}$2"
  else
    curl -sS -X "$1" -H "Authorization: Bearer $RUNPOD_API_KEY" "${API}$2"
  fi
}

j() { python3 -c "import json,sys; d=json.load(sys.stdin); $1" 2>/dev/null || echo "" ; }

echo "=== [1/4] create network volume + app-pod (multi-DC fallback)"
# A volume is bound to one DC. If that DC has no CPU capacity the pod create
# fails and the volume would bill forever. So we try DCs in order: create
# volume + pod together, and on pod-create failure DELETE the volume before
# moving on. A pre-existing RUNPOD_DB_VOLUME_ID is reused (data preserved)
# and pins us to its DC.
DC_CANDIDATES=("$DC" US-WA-1 US-NE-1 US-TX-3 US-IL-1 US-KS-2 US-MO-1 US-MO-2 US-NC-2 US-CA-2 EU-FR-1 EU-NL-1 EU-CZ-1 EU-RO-1 CA-MTL-3 CA-MTL-4 AP-JP-1)
DC_TRY=()
seen=""
for d in "${DC_CANDIDATES[@]}"; do
  if [[ ":$seen:" != *":$d:"* ]]; then DC_TRY+=("$d"); seen="$seen:$d"; fi
done

VOLUME_ID=""
APP_POD_ID=""

if [ -n "${RUNPOD_DB_VOLUME_ID:-}" ]; then
  echo "    reusing existing RUNPOD_DB_VOLUME_ID=${RUNPOD_DB_VOLUME_ID} (data preserved)"
  VOLUME_ID="$RUNPOD_DB_VOLUME_ID"
  DC_TRY=("${RUNPOD_DC:-$DC}")  # volume is bound to its DC
fi

for dc in "${DC_TRY[@]}"; do
  echo "  --- dc=${dc} ---"
  if [ -z "$VOLUME_ID" ]; then
    vol_resp=$(api POST /networkvolumes "{\"name\":\"tracker-data-vol\",\"size\":${VOLUME_SIZE_GB},\"dataCenterId\":\"${dc}\"}")
    VOLUME_ID=$(echo "$vol_resp" | j 'print(d.get("id",""))')
    if [ -z "$VOLUME_ID" ]; then
      echo "    volume create failed in ${dc}: ${vol_resp:0:200}"
      continue
    fi
    echo "    volume id: $VOLUME_ID (dc=${dc})"
  fi

  # cpuFlavorIds is mandatory; valid: cpu3c|cpu3g|cpu3m|cpu5c|cpu5g|cpu5m.
  for spec in '"vcpuCount":4' '"vcpuCount":2' '"vcpuCount":8'; do
    app_body=$(cat <<JSON
{
  "name": "tracker-app",
  "cloudType": "SECURE",
  "computeType": "CPU",
  "cpuFlavorIds": ["cpu3g", "cpu5g", "cpu3c", "cpu5c", "cpu3m", "cpu5m"],
  "cpuFlavorPriority": "availability",
  "imageName": "runpod/base:0.6.2-cpu",
  ${spec},
  "containerDiskInGb": 30,
  "networkVolumeId": "${VOLUME_ID}",
  "volumeMountPath": "${DATA_MOUNT}",
  "ports": ["8050/http", "22/tcp"],
  "supportPublicIp": true,
  "env": { "PUBLIC_KEY": "${PUBKEY}" }
}
JSON
)
    app_resp=$(api POST /pods "$app_body")
    APP_POD_ID=$(echo "$app_resp" | j 'print(d.get("id",""))')
    if [ -n "$APP_POD_ID" ]; then
      echo "    app-pod id: $APP_POD_ID (dc=${dc}, ${spec})"
      DC="$dc"
      break 2
    fi
    echo "    ${spec} in ${dc}: ${app_resp:0:120}..."
  done

  # All specs exhausted for this DC. Drop a volume we created here so it
  # does not bill while we try other DCs.
  if [ -z "${RUNPOD_DB_VOLUME_ID:-}" ] && [ -n "$VOLUME_ID" ]; then
    echo "    delete volume $VOLUME_ID (dc=${dc} exhausted)"
    api DELETE "/networkvolumes/${VOLUME_ID}" >/dev/null || true
    VOLUME_ID=""
  fi
done

[ -n "$APP_POD_ID" ] || { echo "FAILED: no DC has CPU capacity; volume left clean"; exit 1; }

# Persist the volume id immediately so a re-run never orphan-bills.
grep -v '^RUNPOD_DB_VOLUME_ID=' "$ENV_FILE" > "${ENV_FILE}.new" 2>/dev/null || true
echo "RUNPOD_DB_VOLUME_ID=${VOLUME_ID}" >> "${ENV_FILE}.new"
mv "${ENV_FILE}.new" "$ENV_FILE"; chmod 600 "$ENV_FILE"

echo "=== [2/4] wait for app-pod RUNNING (up to 4 min)"
for i in $(seq 1 48); do
  s=$(api GET "/pods/$APP_POD_ID" | j 'print(d.get("desiredStatus") or d.get("status") or "?")')
  echo "  +$((i*5))s  app-pod: $s"
  [ "$s" = "RUNNING" ] && break
  sleep 5
done
[ "$(api GET "/pods/$APP_POD_ID" | j 'print(d.get("desiredStatus") or "")')" = "RUNNING" ] \
  || { echo "FAILED: app-pod not RUNNING after 4min"; exit 1; }

echo "=== [3/4] resolve app SSH endpoint"
# Port mappings show up in the top-level `portMappings` map ({"22": 37405})
# with the host in `publicIp`. `runtime.ports` is often empty even when the
# mapping exists, so prefer portMappings + publicIp and only fall back to
# runtime.ports. Mappings can lag RUNNING by ~30-60s, so poll.
resolve_ssh() {
  api GET "/pods/$APP_POD_ID" | python3 -c "
import json,sys
d = json.load(sys.stdin)
ip = d.get('publicIp') or ''
pm = d.get('portMappings') or {}
port = pm.get('22') or pm.get(22) or ''
if not port:
    for p in (d.get('runtime') or {}).get('ports') or []:
        if int(p.get('privatePort',0)) == 22:
            ip = p.get('ip','') or ip; port = p.get('publicPort',''); break
print(f'{ip} {port}')
"
}
APP_SSH_HOST=""; APP_SSH_PORT=""
for i in $(seq 1 18); do
  read APP_SSH_HOST APP_SSH_PORT <<<"$(resolve_ssh)"
  [ -n "$APP_SSH_HOST" ] && [ -n "$APP_SSH_PORT" ] && break
  echo "  +$((i*5))s  waiting for SSH port mapping..."
  sleep 5
done
echo "    app-pod SSH -> $APP_SSH_HOST:$APP_SSH_PORT"
[ -n "$APP_SSH_HOST" ] && [ -n "$APP_SSH_PORT" ] || { echo "FAILED: missing SSH endpoint"; exit 1; }

echo "=== [4/4] persist to ${ENV_FILE}"
{
  grep -vE '^(RUNPOD_(APP_POD_ID|DB_POD_ID|DB_VOLUME_ID)|APP_POD_SSH_(HOST|PORT)|DB_POD_(HOST|PORT)|DATABASE_URL|BLOB_STORE_DIR|PG_PASSWORD)=' "$ENV_FILE" 2>/dev/null || true
  echo ""
  echo "# Added by scripts/runpod-provision.sh on $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "RUNPOD_APP_POD_ID=${APP_POD_ID}"
  echo "RUNPOD_DB_VOLUME_ID=${VOLUME_ID}"
  echo "RUNPOD_DC=${DC}"
  echo "APP_POD_SSH_HOST=${APP_SSH_HOST}"
  echo "APP_POD_SSH_PORT=${APP_SSH_PORT}"
  echo "PG_PASSWORD=${PG_PASSWORD}"
  echo "DATABASE_URL=postgresql+psycopg://tracker:${PG_PASSWORD}@127.0.0.1:5432/tracker"
  echo "BLOB_STORE_DIR=${DATA_MOUNT}/blobs"
} > "${ENV_FILE}.new"
mv "${ENV_FILE}.new" "$ENV_FILE"
chmod 600 "$ENV_FILE"

cat <<EOF

=== provision OK (durable single-pod + volume)
  app pod id  : $APP_POD_ID    (proxy URL: https://${APP_POD_ID}-8050.proxy.runpod.net)
  volume id   : $VOLUME_ID    (mounted at ${DATA_MOUNT}; survives pod death)
  app SSH     : ssh -p ${APP_SSH_PORT} -i ~/.ssh/id_ed25519 root@${APP_SSH_HOST}
  data        : Postgres -> ${DATA_MOUNT}/pgdata   blobs -> ${DATA_MOUNT}/blobs

next: bash scripts/bootstrap-app-pod.sh
EOF
