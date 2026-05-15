PY := .venv/bin/python
PIP := .venv/bin/pip
ALEMBIC := .venv/bin/alembic
PYTEST := .venv/bin/pytest

.PHONY: venv install db-up db-down migrate test run codegen deploy pod-recover

venv:
	python3.12 -m venv .venv

# `.[dev]` is sufficient: the hermes runtime deps (openai, anthropic,
# pyyaml, httpx) now live in [project].dependencies, so this single
# install covers everything the storage-router needs at runtime.
install: venv
	$(PIP) install -e '.[dev]'

# Reproducible pod deploy — see scripts/deploy.sh for the full sequence.
deploy:
	bash scripts/deploy.sh

# Wake a paused/stopped RunPod pod via the REST API — see
# scripts/runpod-recover.sh. Needs RUNPOD_API_KEY + RUNPOD_POD_ID
# (in .env.local). Use when the pod is in a non-RUNNING state on
# RunPod's side (e.g. "resume failed: not enough host memory").
pod-recover:
	bash scripts/runpod-recover.sh

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	$(ALEMBIC) upgrade head

test:
	$(PYTEST) -xvs tests/

run:
	$(PY) -m storage_router.main

codegen:
	bash scripts/codegen_models.sh
