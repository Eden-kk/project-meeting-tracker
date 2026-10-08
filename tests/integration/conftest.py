"""Isolated PostgreSQL schemas; never use the application's configured DB."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from storage_router import dispatcher, hermes_runtime, import_worker
from storage_router.api import app as app_module, import_route, import_jobs_route
from storage_router.models.db import Base, User, Workspace


@pytest.fixture
def isolated_db(monkeypatch, request):
    value = os.environ.get("MEETING_TEST_DATABASE_URL")
    if not value:
        pytest.skip("set MEETING_TEST_DATABASE_URL to a disposable local PostgreSQL")
    url = make_url(value)
    if (url.drivername != "postgresql+psycopg" or url.query
            or url.host not in {"127.0.0.1", "localhost"}
            or url.database != "meeting_hardening_test"):
        pytest.fail("only local database meeting_hardening_test is permitted")
    schema = "test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        if getattr(request, "param", None) == "migrations":
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=Path(__file__).parents[2],
                env={**os.environ, "DATABASE_URL": value, "PGOPTIONS": f"-csearch_path={schema}"},
                check=True, capture_output=True, text=True,
            )
        else:
            Base.metadata.create_all(engine)
        with factory.begin() as session:
            if session.get(Workspace, "ws_dev") is None:
                session.add(Workspace(id="ws_dev", name="Synthetic tests"))
                session.flush()
                session.add(User(id="u_dev", workspace_id="ws_dev", email="test@example.invalid"))
        for module in (dispatcher, import_worker, import_route, import_jobs_route):
            monkeypatch.setattr(module, "SessionLocal", factory)
        monkeypatch.setattr(app_module, "engine", engine)
        monkeypatch.setattr(hermes_runtime, "auto_finalize_meeting", lambda _: None)
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
