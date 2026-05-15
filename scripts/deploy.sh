#!/usr/bin/env bash
# Reproducible storage-router deploy for the RunPod pod.
#
# Replaces the ad-hoc SSH one-liners. Idempotent: safe to re-run.
# Run ON the pod, from the repo root:  bash scripts/deploy.sh
#
# What it does, in order:
#   1. git fetch + hard-reset to origin/<REF> (default: main)
#   2. repair the .venv / node_modules symlinks if they point nowhere
#      (they are tracked symlinks aimed at a sibling worktree that does
#      not exist on the pod — every `git reset` re-breaks them)
#   3. ensure a complete Python venv: `pip install -e '.[dev]'` — which,
#      since the hermes runtime deps now live in [project].dependencies,
#      pulls everything the in-process hermes_plugin needs (openai,
#      anthropic, pyyaml, httpx). No separate requirements-hermes.txt step.
#   4. pnpm install + pnpm build  (SPA dist)
#   5. alembic upgrade head
#   6. restart uvicorn on :8050, reusing the env of the process it replaces
#      (falls back to .env.local + standard exports if nothing is running)
#   7. health check
#
# Env overrides:
#   DEPLOY_REF   git ref to deploy           (default: main)
#   APP_DIR      repo root on the pod        (default: /workspace/app)
#   APP_PORT     uvicorn port                (default: 8050)
#   APP_LOG      uvicorn log file            (default: /var/log/storage-router.log)
set -euo pipefail

DEPLOY_REF="${DEPLOY_REF:-main}"
APP_DIR="${APP_DIR:-/workspace/app}"
APP_PORT="${APP_PORT:-8050}"
APP_LOG="${APP_LOG:-/var/log/storage-router.log}"

cd "$APP_DIR"

echo "=== [1/7] git fetch + reset to origin/${DEPLOY_REF}"
git fetch origin "$DEPLOY_REF"
git reset --hard "origin/${DEPLOY_REF}"
git log --oneline -1

echo "=== [2/7] repair broken venv / node_modules symlinks"
# These are tracked symlinks → ../<sibling-worktree>/... which does not
# exist on the pod. If they are symlinks (broken or not), drop them so the
# real directories below take their place.
[ -L .venv ] && rm -f .venv
[ -L node_modules ] && rm -f node_modules

echo "=== [3/7] python venv + deps"
if [ ! -x .venv/bin/python ]; then
  python3.12 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
fi
.venv/bin/pip install --quiet -e '.[dev]'
# Sanity: the in-process hermes deps must import.
.venv/bin/python -c 'import openai, anthropic, yaml, httpx' \
  && echo "    hermes runtime deps OK"

echo "=== [4/7] frontend build"
pnpm install --silent
pnpm build 2>&1 | tail -3

echo "=== [5/7] alembic upgrade head"
# DATABASE_URL must be in the environment; source .env.local if present.
[ -f .env.local ] && { set -a; . ./.env.local; set +a; }
.venv/bin/alembic upgrade head 2>&1 | tail -3

echo "=== [6/7] restart uvicorn on :${APP_PORT}"
OLD_PID="$(ss -tlnp 2>/dev/null | grep ":${APP_PORT} " \
            | grep -oP 'pid=\K[0-9]+' | head -1 || true)"
if [ -n "$OLD_PID" ]; then
  echo "    capturing env from running pid ${OLD_PID}"
  # Reuse the live process's environment so we don't drift secrets.
  xargs -0 -n1 -a "/proc/${OLD_PID}/environ" 2>/dev/null \
    | grep -E '^(DATABASE_URL|OPENAI_API_KEY|ANTHROPIC_API_KEY|LLM_PROVIDER|STORAGE_ROUTER_URL|INGEST_BACKEND|VOICE_INGEST_URL|TRANSCRIPT_INGEST_URL|FRONTEND_DIST|PYTHONPATH|ZOOM_[A-Z_]+)=' \
    | sed 's/=\(.*\)/="\1"/' > /tmp/deploy.env.shell
  kill "$OLD_PID"; sleep 3
else
  echo "    no running uvicorn — bootstrapping env from .env.local + defaults"
  {
    grep -E '^(DATABASE_URL|OPENAI_API_KEY|ANTHROPIC_API_KEY)=' .env.local 2>/dev/null || true
    echo "LLM_PROVIDER=\"openai\""
    echo "INGEST_BACKEND=\"real\""
    echo "VOICE_INGEST_URL=\"https://hao-ai-lab--voice-ingest-fastapi.modal.run\""
    echo "TRANSCRIPT_INGEST_URL=\"http://127.0.0.1:8011\""
    echo "STORAGE_ROUTER_URL=\"http://127.0.0.1:${APP_PORT}\""
    echo "FRONTEND_DIST=\"${APP_DIR}/dist\""
    echo "PYTHONPATH=\"${APP_DIR}/src\""
  } > /tmp/deploy.env.shell
fi
set -a; . /tmp/deploy.env.shell; set +a
nohup .venv/bin/uvicorn storage_router.api.app:create_app \
  --factory --host 0.0.0.0 --port "${APP_PORT}" \
  >> "$APP_LOG" 2>&1 &
disown
sleep 6

echo "=== [7/7] health check"
if ss -tlnp 2>/dev/null | grep -q ":${APP_PORT} "; then
  code="$(curl -s -o /dev/null -w '%{http_code}' \
            "http://127.0.0.1:${APP_PORT}/api/workspaces" --max-time 8 || echo 000)"
  echo "    uvicorn listening on :${APP_PORT}, /api/workspaces -> ${code}"
  [ "$code" = "200" ] && echo "=== deploy OK" || {
    echo "=== deploy WARNING: app up but /api/workspaces returned ${code}"
    tail -15 "$APP_LOG"; exit 1
  }
else
  echo "=== deploy FAILED: nothing listening on :${APP_PORT}"
  tail -20 "$APP_LOG"; exit 1
fi
