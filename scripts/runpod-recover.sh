#!/usr/bin/env bash
# Recover a stopped/paused RunPod pod via the RunPod REST API.
#
# Usage:
#   RUNPOD_API_KEY=... RUNPOD_POD_ID=riz0b05s7yg7ab bash scripts/runpod-recover.sh
#   bash scripts/runpod-recover.sh         # reads both from .env.local
#
# Strategy:
#   1. Probe pod status via /v1/pods/{id}.
#   2. If RUNNING but http unreachable → exit, that's a deploy bug, not infra.
#   3. If EXITED / paused → POST /v1/pods/{id}/start, retry up to 5 times
#      over ~10 min with exponential backoff. RunPod's "no host memory"
#      error usually clears as other tenants release RAM.
#   4. If still stuck after 5 tries → fall back to stop+start which lets
#      RunPod re-schedule on a different host. Public proxy URL stays the
#      same (it's keyed on pod ID, not host).
#   5. Once running, wait up to 90s for SSH/HTTP to come back, then exit.
#
# Caller's responsibility AFTER this script returns: run scripts/deploy.sh
# (the pod's processes don't auto-start; only the container's init does).
#
# Docs: https://docs.runpod.io/api-reference/pods/

set -euo pipefail

API="${RUNPOD_API_BASE:-https://rest.runpod.io/v1}"

# --- credentials ----------------------------------------------------------
if [ -z "${RUNPOD_API_KEY:-}" ] || [ -z "${RUNPOD_POD_ID:-}" ]; then
  if [ -f .env.local ]; then
    # shellcheck disable=SC1091
    set -a; . ./.env.local; set +a
  fi
fi
: "${RUNPOD_API_KEY:?missing RUNPOD_API_KEY (set in .env.local or env)}"
: "${RUNPOD_POD_ID:?missing RUNPOD_POD_ID (set in .env.local or env, e.g. riz0b05s7yg7ab)}"

curl_api() {
  # $1=method  $2=path
  curl -sS -X "$1" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    -H 'Content-Type: application/json' \
    "${API}$2"
}

pod_status() {
  curl_api GET "/pods/${RUNPOD_POD_ID}" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("desiredStatus") or d.get("status") or "UNKNOWN")' \
      2>/dev/null || echo "UNKNOWN"
}

pod_public_url() {
  # Derive the deterministic RunPod proxy URL from the pod id + the
  # storage-router port. Pods retain their proxy host across stop/start.
  echo "https://${RUNPOD_POD_ID}-8050.proxy.runpod.net"
}

probe_http() {
  curl -s -o /dev/null --max-time 5 --connect-timeout 3 \
    -w '%{http_code}' "$(pod_public_url)/api/workspaces" 2>/dev/null || echo 000
}

# --- main -----------------------------------------------------------------
echo "=== [1/4] probe pod ${RUNPOD_POD_ID} via RunPod API"
status=$(pod_status)
http=$(probe_http)
echo "    api: ${status}    http: ${http}"

if [ "$status" = "RUNNING" ] && [ "$http" = "200" ]; then
  echo "=== pod is healthy already, nothing to do"
  exit 0
fi
if [ "$status" = "RUNNING" ] && [ "$http" != "200" ]; then
  echo "=== pod is RUNNING but http=${http} — uvicorn down, run scripts/deploy.sh"
  exit 2
fi

echo "=== [2/4] attempt to start (5 tries, exp backoff)"
delay=5
for i in 1 2 3 4 5; do
  echo "  try ${i}: POST /pods/${RUNPOD_POD_ID}/start"
  resp=$(curl_api POST "/pods/${RUNPOD_POD_ID}/start" || true)
  echo "    -> ${resp:0:200}"
  sleep "$delay"
  status=$(pod_status)
  echo "    pod status: ${status}"
  if [ "$status" = "RUNNING" ]; then break; fi
  delay=$((delay * 2))
done

if [ "$status" != "RUNNING" ]; then
  echo "=== [3/4] start retries exhausted — falling back to stop + start (re-schedule)"
  curl_api POST "/pods/${RUNPOD_POD_ID}/stop" >/dev/null || true
  sleep 15
  for i in 1 2 3; do
    echo "  cold-start try ${i}: POST /pods/${RUNPOD_POD_ID}/start"
    curl_api POST "/pods/${RUNPOD_POD_ID}/start" >/dev/null || true
    sleep 15
    status=$(pod_status)
    echo "    pod status: ${status}"
    if [ "$status" = "RUNNING" ]; then break; fi
  done
fi

if [ "$status" != "RUNNING" ]; then
  echo "=== FAILED: pod still not RUNNING (status=${status}). RunPod likely has"
  echo "    no capacity in the region. Move the pod to another region/template"
  echo "    in the RunPod console, or wait + retry later."
  exit 1
fi

echo "=== [4/4] pod RUNNING — wait up to 90s for http to come back"
for i in $(seq 1 18); do
  http=$(probe_http)
  echo "  +$((i*5))s  http=${http}"
  if [ "$http" = "200" ] || [ "$http" = "404" ]; then break; fi
  sleep 5
done

if [ "$http" = "200" ]; then
  echo "=== pod recovered, http 200"
elif [ "$http" = "404" ]; then
  echo "=== pod up, proxy reachable, but uvicorn not running. Now run:"
  echo "    bash scripts/deploy.sh   (on the pod via SSH)"
else
  echo "=== pod up per API but http=${http}. May need SSH manually to investigate."
fi
