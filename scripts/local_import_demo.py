"""Disposable loopback demo: real PostgreSQL/API, deterministic fake model output.

Requires MEETING_TEST_DATABASE_URL pointing to the local meeting_hardening_test DB.
Never use this harness as a production entry point.
"""
import os
from pathlib import Path
import subprocess
import sys
import signal
import time
import uuid
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    value = os.environ["MEETING_TEST_DATABASE_URL"]
    url = make_url(value)
    if (url.drivername != "postgresql+psycopg" or url.query
            or url.host not in {"127.0.0.1", "localhost"}
            or url.database != "meeting_hardening_test"):
        raise ValueError("Only disposable local meeting_hardening_test DB is allowed")
    schema = "demo_" + uuid.uuid4().hex
    root = Path(__file__).resolve().parents[1]
    scratch = TemporaryDirectory(prefix="meeting-demo-")
    os.environ.update(DATABASE_URL=value, PGOPTIONS=f"-csearch_path={schema}",
                      INGEST_BACKEND="stub", FRONTEND_DIST=str(root / "dist"),
                      BLOB_STORE_DIR=scratch.name)
    admin = create_engine(url, connect_args={"options": "-csearch_path=public"})
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=root, check=True)
        import uvicorn
        from storage_router import dispatcher, hermes_runtime
        from storage_router.api.app import create_app
        from storage_router.db import engine
        from fastapi.routing import APIRoute

        original_parse = dispatcher.parse_transcript

        def delayed_parse(*args, **kwargs):
            time.sleep(3)  # Deliberate cancellation window, not a latency benchmark.
            return original_parse(*args, **kwargs)

        dispatcher.parse_transcript = delayed_parse
        hermes_runtime.run_meeting_finalization = lambda _: {
            "summary": "OFFLINE DEMO: deterministic fixture, no model invoked.", "cards": []}
        app = create_app()
        # Do not let exploration of the full SPA invoke Q&A/live/follow-up/Zoom
        # routes with credentials that may exist in the developer's env file.
        allowed = {
            ("GET", "/api/workspaces"), ("GET", "/api/meetings"),
            ("GET", "/api/meetings/{meeting_id}"),
            ("GET", "/api/meetings/{meeting_id}/transcript"),
            ("GET", "/api/meetings/{meeting_id}/memory-cards"),
            ("POST", "/api/conversations/import"),
            ("GET", "/api/meetings/{meeting_id}/import-job"),
            ("POST", "/api/meetings/{meeting_id}/import-job/cancel"),
            ("POST", "/api/meetings/{meeting_id}/import-job/retry"),
        }
        app.router.routes[:] = [route for route in app.router.routes
            if not isinstance(route, APIRoute) or not route.path.startswith("/api/")
            or all((method, route.path) in allowed for method in route.methods)]
        print("OFFLINE DEMO ONLY: synthetic transcription/finalization; local DB schema", schema)
        # Uvicorn restores and re-raises SIGTERM after graceful shutdown. The
        # default handler exits immediately, bypassing Python finally blocks.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        try:
            uvicorn.run(app, host="127.0.0.1", port=18765)
        finally:
            engine.dispose()
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
        scratch.cleanup()


if __name__ == "__main__":
    main()
