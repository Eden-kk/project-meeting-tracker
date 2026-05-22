#!/usr/bin/env bash
# First-time bootstrap of a freshly-provisioned app pod.
#
# Runs FROM the workstation, SSH-driving the new app pod:
#   1. Wait for SSH to come up.
#   2. apt-get install Python 3.12, Node, pnpm, pulseaudio, ffmpeg.
#   3. git clone the repo to /workspace/app.
#   4. Write /workspace/app/.env.local from the workstation's values
#      (DATABASE_URL + API keys + ZOOM_* if present).
#   5. Run scripts/deploy.sh on the pod — the same one we use for any
#      redeploy; it builds the SPA, alembic upgrades, starts uvicorn.
#
# Inputs read from .env.local (gitignored on the workstation):
#   APP_POD_SSH_HOST, APP_POD_SSH_PORT  (written by runpod-provision.sh)
#   DATABASE_URL                         (written by runpod-provision.sh)
#   OPENAI_API_KEY, ANTHROPIC_API_KEY    (from your existing setup)
#   ZOOM_SDK_KEY, ZOOM_SDK_SECRET,
#   ZOOM_OAUTH_CLIENT_ID, ZOOM_OAUTH_CLIENT_SECRET  (optional)

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env.local}"
[ -f "$ENV_FILE" ] && { set -a; . "./${ENV_FILE}"; set +a; }

: "${APP_POD_SSH_HOST:?missing APP_POD_SSH_HOST — run scripts/runpod-provision.sh first}"
: "${APP_POD_SSH_PORT:?missing APP_POD_SSH_PORT — run scripts/runpod-provision.sh first}"
: "${DATABASE_URL:?missing DATABASE_URL — run scripts/runpod-provision.sh first}"
: "${OPENAI_API_KEY:?missing OPENAI_API_KEY in .env.local}"
: "${ANTHROPIC_API_KEY:?missing ANTHROPIC_API_KEY in .env.local}"

REPO_URL="${REPO_URL:-https://github.com/Eden-kk/project-meeting-tracker.git}"
REPO_REF="${REPO_REF:-main}"

POD="root@${APP_POD_SSH_HOST}"
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p ${APP_POD_SSH_PORT} -i ${HOME}/.ssh/id_ed25519 ${POD}"

echo "=== [1/5] wait for ssh on ${APP_POD_SSH_HOST}:${APP_POD_SSH_PORT}"
for i in $(seq 1 24); do
  if $SSH 'echo OK' 2>/dev/null | grep -q OK; then echo "    SSH up"; break; fi
  echo "    +$((i*5))s  not yet"; sleep 5
done
$SSH 'echo OK' 2>/dev/null | grep -q OK || { echo "FAILED: ssh never came up"; exit 1; }

echo "=== [2/6] install toolchain: python3.12 (via uv), node20, pnpm, ffmpeg"
# Python 3.12 comes from uv, NOT the deadsnakes PPA: on runpod/base (Ubuntu
# 20.04 focal) the deadsnakes index accepts InRelease but never serves the
# python3.12 Packages, so `apt-get install python3.12-venv` fails. uv pulls
# a self-contained CPython 3.12 build with no apt/PPA/GPG dependency.
$SSH 'set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q curl ca-certificates git pulseaudio ffmpeg postgresql-client cron
  if ! command -v python3.12 >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    uv python install 3.12
    ln -sf "$(uv python find 3.12)" /usr/local/bin/python3.12
  fi
  # Node 20 + pnpm
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -q nodejs
  npm install -g -s pnpm
  python3.12 --version; node --version; pnpm --version
'

echo "=== [3/5] git clone to /workspace/app"
$SSH "set -e
  mkdir -p /workspace
  if [ -d /workspace/app/.git ]; then
    cd /workspace/app && git fetch origin ${REPO_REF} && git reset --hard origin/${REPO_REF}
  else
    git clone --depth 50 -b ${REPO_REF} ${REPO_URL} /workspace/app
  fi
  cd /workspace/app && git log --oneline -1
"

echo "=== [4/6] write /workspace/app/.env.local on the pod"
# Build the contents locally, then scp it. NEVER pass secrets on the
# command line — they'd land in /proc/$pid/cmdline.
TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT
{
  echo "DATABASE_URL=${DATABASE_URL}"
  echo "BLOB_STORE_DIR=${BLOB_STORE_DIR:-/data/blobs}"
  # PG_PASSWORD is needed only for the FIRST init of a fresh volume;
  # setup-data-volume.sh stores it on the volume afterwards.
  [ -n "${PG_PASSWORD:-}" ]             && echo "PG_PASSWORD=${PG_PASSWORD}"
  echo "OPENAI_API_KEY=${OPENAI_API_KEY}"
  echo "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"
  [ -n "${ZOOM_SDK_KEY:-}" ]            && echo "ZOOM_SDK_KEY=${ZOOM_SDK_KEY}"
  [ -n "${ZOOM_SDK_SECRET:-}" ]         && echo "ZOOM_SDK_SECRET=${ZOOM_SDK_SECRET}"
  [ -n "${ZOOM_OAUTH_CLIENT_ID:-}" ]    && echo "ZOOM_OAUTH_CLIENT_ID=${ZOOM_OAUTH_CLIENT_ID}"
  [ -n "${ZOOM_OAUTH_CLIENT_SECRET:-}" ] && echo "ZOOM_OAUTH_CLIENT_SECRET=${ZOOM_OAUTH_CLIENT_SECRET}"
} > "$TMP_ENV"
scp -o StrictHostKeyChecking=no -P "$APP_POD_SSH_PORT" \
    -i "${HOME}/.ssh/id_ed25519" \
    "$TMP_ENV" "${POD}:/workspace/app/.env.local"
$SSH 'chmod 600 /workspace/app/.env.local'

echo "=== [5/6] init Postgres + blobs on the network volume (/data)"
# Idempotent: fresh volume -> initdb + create role/db; re-attached volume
# -> just start the existing cluster (data preserved).
$SSH 'cd /workspace/app && set -a && . ./.env.local && set +a && DATA_DIR=/data bash scripts/setup-data-volume.sh'

echo "=== [6/6] run scripts/deploy.sh on the pod"
$SSH 'cd /workspace/app && bash scripts/deploy.sh' | tail -25

cat <<EOF

=== app pod bootstrapped
  proxy URL : https://${RUNPOD_APP_POD_ID:-<podid>}-8050.proxy.runpod.net
  ssh       : ssh -p ${APP_POD_SSH_PORT} -i ~/.ssh/id_ed25519 root@${APP_POD_SSH_HOST}

next:
  - verify the proxy URL in a browser
  - if Zoom integration is wanted, set ZOOM_SDK_KEY/SECRET + ZOOM_OAUTH_*
    in .env.local on the workstation, then re-run this script (it is
    idempotent — the deploy step picks up the new env on restart).
EOF
