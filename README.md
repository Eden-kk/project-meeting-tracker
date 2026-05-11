# storage-router (Worktree D)

FastAPI artifact router + storage boundary for the Tracker Phase-1 MVP.
Owns `POST /api/conversations/import`, `GET /api/meetings/{id}`,
`GET /api/meetings/{id}/transcript`, the Postgres schema (Alembic), and
the blob-storage adapter.

## Bootstrap

Requires Python 3.12 and a reachable Postgres 16 instance.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

### Database

The DSN is read from `DATABASE_URL`. In this environment a managed
Postgres is already provisioned and its DSN lives in `.env.local`
(gitignored, mode 600). The project loads `.env.local` automatically via
`python-dotenv` when present, so you only need:

```bash
# verify
.venv/bin/python -c "from storage_router.config import settings; print(settings.database_url)"
```

If you are on a fresh checkout without `.env.local`, copy `.env.example`
to `.env.local` and edit, or start the bundled compose Postgres:

```bash
docker compose up -d postgres
cp .env.example .env.local  # then edit DATABASE_URL if needed
```

### Migrations

```bash
.venv/bin/alembic upgrade head
```

### Tests

```bash
.venv/bin/pytest -xvs tests/
```

Tests run against the live Postgres in `DATABASE_URL` and clean up data
they create — they do not drop tables.

### Run the server

```bash
.venv/bin/uvicorn storage_router.api.app:create_app --factory --port 8000
```
