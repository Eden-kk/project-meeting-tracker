#!/usr/bin/env bash
# Start the wave8-8.6 storage-router with settings sourced from .env.local
set -euo pipefail

ROOT=/home/yid042/projects/project-meeting-tracker
WORKTREE="$ROOT/.worktrees/wave8-8.6"

# Source the env (pick up DATABASE_URL, API keys, etc.)
set -a
source "$ROOT/.env.local"
set +a

# Wave8-specific overrides
export PYTHONPATH="$WORKTREE/src"
export LLM_PROVIDER=openai
export INGEST_BACKEND=real
export VOICE_INGEST_URL=http://127.0.0.1:8021
export TRANSCRIPT_INGEST_URL=http://127.0.0.1:8011
export FRONTEND_DIST="$WORKTREE/dist"
export STORAGE_ROUTER_URL=http://127.0.0.1:8050

cd "$WORKTREE"
exec .venv/bin/uvicorn storage_router.api.app:create_app \
    --factory --host 127.0.0.1 --port 8050 \
    >> /tmp/storage-router-wave8.log 2>&1
