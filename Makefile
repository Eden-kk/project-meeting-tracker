PY := .venv/bin/python
PIP := .venv/bin/pip
ALEMBIC := .venv/bin/alembic
PYTEST := .venv/bin/pytest

.PHONY: venv install db-up db-down migrate test run codegen

venv:
	python3.12 -m venv .venv

install: venv
	$(PIP) install -e '.[dev]'

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
