# Pod deployment handbook

How the production deployment runs on the RunPod pod, how to deploy to
it, and the failure modes that have actually bitten us — with the fix
for each. Read this before touching the pod.

## 1. Topology

```
                         browser
                            │
                            ▼
        https://riz0b05s7yg7ab-8050.proxy.runpod.net   (Cloudflare → RunPod proxy)
                            │
                            ▼
        storage-router  —  uvicorn 0.0.0.0:8050  (factory: storage_router.api.app:create_app)
        ├── /              → built SPA from $FRONTEND_DIST
        ├── /docs          → FastAPI Swagger
        ├── /api/*         → JSON endpoints
        │
        ├── Postgres        127.0.0.1:5432   (internal to the pod)
        ├── transcript-ingest 127.0.0.1:8011 (uvicorn, same venv)
        └── voice-ingest    https://hao-ai-lab--voice-ingest-fastapi.modal.run  (Modal, NOT on the pod)
```

- **The pod is a RunPod host**, SSH-reachable at `root@213.192.2.103:41734`.
- **App lives at `/workspace/app`** on the pod (a normal git checkout of this repo).
- **Postgres runs inside the pod** on loopback `127.0.0.1:5432`. It is
  *not* reachable from outside the pod — see issue #4.
- **voice-ingest is NOT on the pod** — it is a Modal app. Diarization /
  Whisper happen there. See `README-voice-ingest.md`.
- **Logs:** storage-router → `/var/log/storage-router.log`,
  transcript-ingest → `/var/log/transcript-ingest.log`.

## 2. Deploying

One command, on the pod, from `/workspace/app`:

```bash
bash scripts/deploy.sh        # or: make deploy
```

`scripts/deploy.sh` is idempotent and does, in order:

1. `git fetch` + hard-reset to `origin/main` (override with `DEPLOY_REF`).
2. Repair the tracked `.venv` / `node_modules` symlinks (issue #1).
3. Ensure a complete Python venv: `pip install -e '.[dev]'` — which now
   pulls every runtime dep including the hermes ones (issue #2).
4. `pnpm install` + `pnpm build` → SPA `dist/`.
5. `alembic upgrade head`.
6. Restart uvicorn on `:8050`, **inheriting only secrets** from the
   process it replaces and **setting operational config
   deterministically** (issue #3).
7. Health check: asserts both `/api/workspaces` **and** `/` return 200
   (the latter catches issue #3).

If any step fails the script exits non-zero and tails the log. A green
run ends with `=== deploy OK`.

### From a workstation

```bash
ssh -p 41734 -i ~/.ssh/id_ed25519 root@213.192.2.103 \
  'cd /workspace/app && git fetch origin main -q && git reset --hard origin/main -q && bash scripts/deploy.sh'
```

The leading `git fetch && reset` is only needed when `scripts/deploy.sh`
itself changed in the commit you are deploying (chicken-and-egg — the
script can't pull a newer copy of itself before running). Otherwise
`bash scripts/deploy.sh` alone suffices, since step 1 does the pull.

## 3. Environment variables

The deploy splits env into two categories. **This split is
load-bearing — do not collapse it** (issue #3).

| Category | Vars | Source |
|---|---|---|
| **Secrets** — cannot be derived | `DATABASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ZOOM_*` | Inherited from the predecessor uvicorn process's `/proc/<pid>/environ`; falls back to `.env.local` if nothing is running. |
| **Operational config** — derivable from the deploy | `FRONTEND_DIST`, `PYTHONPATH`, `STORAGE_ROUTER_URL`, `INGEST_BACKEND`, `VOICE_INGEST_URL`, `TRANSCRIPT_INGEST_URL`, `LLM_PROVIDER` | **Always set deterministically** by `deploy.sh`. Never inherited. |

`.env.local` on the pod holds the secrets and is the bootstrap source
when no process is running. It is gitignored — never commit it.

## 4. Known issues & fixes

Each of these has bitten production. The fix is in the repo; this
section is the institutional memory for *why* the code looks the way
it does.

### Issue #1 — tracked `.venv` / `node_modules` symlinks break on every `git reset`

`.venv` and `node_modules` are committed to the repo as **symlinks**
pointing at `../<sibling-worktree>/...` (an artifact of the original
parallel-worktree dev setup). That sibling path does not exist on the
pod, so the symlinks dangle. Every `git reset --hard` restores them,
re-breaking the venv and node_modules lookup.

**Fix:** `deploy.sh` step 2 detects `[ -L .venv ]` / `[ -L node_modules ]`
and `rm`s them, so the real directories created in steps 3–4 take their
place. If you ever deploy *without* the script, you must do this by hand
or every binary lookup (`uvicorn`, `alembic`, `tsc`, `vite`) fails with
"No such file or directory".

### Issue #2 — `pip install -e '.[dev]'` didn't pull hermes runtime deps → finalize 500s

`storage_router.hermes_runtime` imports `hermes_plugin` **in-process**.
The hermes runtime deps (`openai`, `anthropic`, `pyyaml`, `httpx`) used
to live only in a `hermes` *optional-extra* that the documented install
(`pip install -e '.[dev]'`) never pulled — and `openai` wasn't even in
that extra. On a fresh pod venv, every `POST /api/meetings/{id}/finalize`
raised `ModuleNotFoundError: No module named 'openai'` → HTTP 500.
Browsing worked (pure DB reads), so the breakage was easy to miss.

**Fix (commit `b19075a`):** the hermes runtime deps were moved into
`[project].dependencies` in `pyproject.toml`. `pip install -e '.[dev]'`
is now sufficient for everything the storage-router needs at runtime.
`deploy.sh` step 3 sanity-checks `import openai, anthropic, yaml, httpx`.

### Issue #3 — `FRONTEND_DIST` not set → SPA 307-redirects to `/docs` ("unusable")

`app.py` registers a `RedirectResponse(url="/docs")` fallback for
`GET /` **when `FRONTEND_DIST` is unset**. An earlier version of
`deploy.sh` inherited the *entire* env of the predecessor process,
including operational config. When the predecessor happened to lack
`FRONTEND_DIST`, the script copied that absence forward — so `GET /`
served a 307 to `/docs` and users saw only the Swagger page, no app.
The SPA `dist/` was built and present; it just was never wired up.

**Fix (commit `1dceb22`):** operational config is now always set
deterministically by `deploy.sh` (see §3); only secrets are inherited.
Plus a pre-flight guard (`${FRONTEND_DIST}/index.html` must exist) and a
health check that asserts `GET /` returns 200, not a redirect.

### Issue #4 — Postgres is reachable from the pod, not from outside

`DATABASE_URL` points at `127.0.0.1:5432` *inside the pod*. From a
workstation CLI you cannot connect — `alembic`, `psql`, and any
SQLAlchemy script run off-pod will fail to connect. Run all DB-touching
work (migrations, `pytest` against a live DB) **on the pod**, or through
the pod's running service via the API.

### Issue #5 — `app.state.live_tasks` was never initialized → shutdown crash

`create_app` initialized `app.state.sentence_buffers` but not
`app.state.live_tasks`, even though the shutdown handler and the
`live_topic_tracker` / `live_interview_questioner` modules all read it.
A process that never ran a live meeting crashed on shutdown with
`AttributeError: 'State' object has no attribute 'live_tasks'`.

**Fix (commit `b19075a`):** `app.state.live_tasks = {}` is initialized
in `create_app` alongside `sentence_buffers`.

### Issue #6 — SSH from automation may be blocked

The Claude Code auto-classifier treats SSH-into-the-pod as a
production-shell action and may block it per-utterance. Not a code bug —
just expect deploys driven through tooling to need an explicit
authorization step, or a `Bash(ssh -*-p 41734 *root@213.192.2.103*:*)`
permission rule in `~/.claude/settings.json`.

## 5. Post-deploy verification checklist

`deploy.sh`'s own health check covers the first two. Run the rest from
anywhere after a deploy:

```bash
BASE=https://riz0b05s7yg7ab-8050.proxy.runpod.net
curl -s -o /dev/null -w '/        -> %{http_code}\n' "$BASE/"                              # want 200 (NOT 307)
curl -s -o /dev/null -w '/api/ws  -> %{http_code}\n' "$BASE/api/workspaces"                # want 200
curl -s "$BASE/" | grep -q 'id="root"' && echo '/        -> serves SPA' || echo '/  -> NOT the SPA'
# finalize on an already-finalized meeting must be 409, never 500
# (500 here = hermes deps missing again, issue #2):
curl -s -o /dev/null -w 'finalize -> %{http_code}\n' -X POST "$BASE/api/meetings/<finalized-id>/finalize"
```

On the pod:

```bash
ss -tlnp | grep 8050                                   # uvicorn listening
.venv/bin/python -c 'import openai, anthropic, yaml, httpx'   # hermes deps present
tail -20 /var/log/storage-router.log                   # clean "Application startup complete"
```

## 6. Recovery — "the site is down / unusable"

1. **SSH in**, check what is actually wrong:
   ```bash
   ss -tlnp | grep 8050                 # is uvicorn even listening?
   tail -40 /var/log/storage-router.log # last error
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8050/   # 200? 307? nothing?
   ```
2. **Most failures are fixed by a clean redeploy:** `bash scripts/deploy.sh`.
   It repairs the symlinks, reinstalls the venv, rebuilds the SPA, and
   restarts with correct env — i.e. it self-heals issues #1, #2, #3, #5.
3. **`307` on `/`** → `FRONTEND_DIST` issue (#3). The corrected
   `deploy.sh` sets it deterministically; just re-run it.
4. **`500` on finalize** → hermes deps missing (#2). Re-run `deploy.sh`;
   step 3 reinstalls and sanity-checks them.
5. **Binary "No such file or directory"** → broken symlinks (#1).
   Re-run `deploy.sh`, or by hand: `rm -f .venv node_modules` then
   recreate.
6. **uvicorn won't start at all** → read the log tail. If it is a DB
   connection error, the pod's Postgres is down — that is infra, not
   code; restart Postgres inside the pod.

## 7. Quick reference

| Thing | Value |
|---|---|
| Public URL | `https://riz0b05s7yg7ab-8050.proxy.runpod.net` |
| SSH | `ssh -p 41734 -i ~/.ssh/id_ed25519 root@213.192.2.103` |
| App dir | `/workspace/app` |
| Deploy | `bash scripts/deploy.sh` (or `make deploy`) |
| storage-router | uvicorn `0.0.0.0:8050`, log `/var/log/storage-router.log` |
| transcript-ingest | uvicorn `127.0.0.1:8011`, log `/var/log/transcript-ingest.log` |
| voice-ingest | Modal: `https://hao-ai-lab--voice-ingest-fastapi.modal.run` |
| Postgres | `127.0.0.1:5432` (pod-internal only) |
| Secrets on pod | `/workspace/app/.env.local` (gitignored) |
