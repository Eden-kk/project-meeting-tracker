PY := .venv/bin/python
PIP := .venv/bin/pip
ALEMBIC := .venv/bin/alembic
PYTEST := .venv/bin/pytest

.PHONY: venv install db-up db-down migrate test run codegen deploy

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
