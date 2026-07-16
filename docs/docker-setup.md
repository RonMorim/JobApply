# Docker Setup

**Status:** Dev-mode Docker Compose setup — mirrors the local `uvicorn --reload` / `npm run dev` workflow
in [`README.md`](../README.md), containerized. This is **not** a production deployment config: no
multi-stage build, no reverse proxy, no TLS, no process manager. It exists so the whole product (FastAPI +
Next.js) can be brought up end-to-end with one command, without needing a local Python/Node toolchain.

Companion docs: [`docs/environment-setup.md`](environment-setup.md) (full dependency inventory, from-clean-state
setup without Docker, Known Issues) and [`CLAUDE.md`](../CLAUDE.md) (architecture).

---

## 1. What's included

| File | Purpose |
|---|---|
| `backend/Dockerfile` | Python 3.9-slim image: installs `backend/requirements.txt`, installs Playwright's Chromium (needed by `backend/services/pdf_builder.py` for resume PDF export), runs `uvicorn --reload`. |
| `backend/.dockerignore` | Keeps `.venv/`, `__pycache__/`, `jobs.db`, and `.env` out of the backend build context. |
| `web_dashboard/Dockerfile` | Node 20 image: `npm install`, runs `npm run dev`. |
| `web_dashboard/.dockerignore` | Keeps `node_modules/`, `.next/`, and `.env.local` out of the frontend build context. |
| `docker-compose.yml` (repo root) | Wires both services together: backend on `:8000`, frontend on `:3000`, bind-mounts for live-reload, a healthcheck gate so the frontend waits for the backend to be ready. |
| `.dockerignore` (repo root) | The *backend* image's build context is the repo root (not `backend/`) because it also needs the shared `models/` package — see §2. This keeps `web_dashboard/`, `.git/`, and the legacy Streamlit app's files out of that context. |

**Not included, on purpose:** Postgres and Redis services. `backend/config.py` reads `DATABASE_URL`/`REDIS_URL`
as placeholders only — nothing in the codebase is wired to them (see `CLAUDE.md` and `backend/.env.example`).
SQLite (`backend/jobs.db`) is the actual, active datastore. Adding unused services would just be dead
infrastructure to maintain.

## 2. Why the backend build context is the repo root

The FastAPI app imports the shared Pydantic models package at the repo root
(`from models.job import RawJobPosting`, etc.) in addition to everything under `backend/` — see
`CLAUDE.md`'s "Shared Pydantic models (`models/`)" section. `backend/Dockerfile` therefore builds with
`context: .` in `docker-compose.yml` and copies only `backend/` + `models/` — not the whole repo (no
`web_dashboard/`, no legacy `app.py`/`orchestrator.py`/root `requirements.txt`, which belong to the frozen
Streamlit reference app per `docs/architecture-boundaries.md`).

## 3. Prerequisites — env files (you fill these in, nothing is created for you)

Docker Compose does **not** create or fill in any secrets. Copy both example files and fill in real values
before running `docker compose up`:

```bash
cp backend/.env.example backend/.env
cp web_dashboard/.env.example web_dashboard/.env.local
```

Then edit both files. At minimum, for the app to boot without warnings and for login to work:

- `backend/.env`: `ANTHROPIC_API_KEY`, and at least one of `SUPABASE_URL` / `SUPABASE_JWT_SECRET`.
- `web_dashboard/.env.local`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (same Supabase
  project as the backend's `SUPABASE_URL`).

Both `.env` and `.env.local` are gitignored — nothing you put in them can end up in a commit by accident.
Full variable reference (what's required vs. optional, and what breaks without each one) is in each
`.env.example` file directly — that's the single source of truth, not this doc.

**`BACKEND_URL`** in `web_dashboard/.env.local` does **not** need to be changed for Docker — the root
`docker-compose.yml` overrides it to `http://backend:8000` automatically at the container level (see the
comment in `web_dashboard/.env.example`).

## 4. Running it

```bash
docker compose up --build
```

- Backend: **http://localhost:8000** — API docs (Swagger) at **http://localhost:8000/docs**.
- Frontend: **http://localhost:3000**.
- First boot creates `backend/jobs.db` from scratch (SQLite) if it doesn't already exist on the host —
  this is a normal, previously-flagged-as-risky path that has since been verified fixed (see
  `docs/environment-setup.md` §3.1). No seed file needed.
- Both services bind-mount their source directories, so editing code on the host live-reloads inside the
  container exactly like running `uvicorn --reload` / `next dev` directly — no rebuild needed for normal
  code changes. A rebuild (`docker compose up --build`) is only needed after changing
  `backend/requirements.txt` or `web_dashboard/package.json`.
- `docker compose down` stops both containers. `backend/jobs.db` persists on the host afterward (it's a
  bind mount, not a container-internal volume) — `docker compose down -v` does **not** delete it, since no
  named volumes are used for it.

## 5. Where to see errors while testing

- **Backend:** `docker compose logs -f backend` (or omit `-f` for a one-shot dump). Same log format/content
  as running `uvicorn` directly — safe-logging discipline still applies (no raw prompts/CV text/model output
  in these logs, per `CLAUDE.md`).
- **Frontend:** `docker compose logs -f frontend` for server-side/build errors; the browser console for
  client-side errors, exactly as with `next dev` outside Docker.

## 6. Known limitations of this setup

- **Playwright/Chromium image size:** `backend/Dockerfile` installs Chromium via `playwright install
  --with-deps`, which pulls in a nontrivial set of apt packages. This is required for resume PDF export
  (`pdf_builder.py`) to work at all — not optional bloat.
- **No hot-reload for `backend/requirements.txt` or `package.json` changes** — those require
  `docker compose up --build`, same as any other Docker Compose dev setup.
- **`STRICT_CONFIG` and `ENVIRONMENT`** behave identically inside Docker as outside it — nothing about
  containerization changes `backend/config.py`'s validation logic. Leave both unset (their defaults) for
  local Docker testing; do not set `ENVIRONMENT=production` unless you've also set `CORS_ALLOWED_ORIGINS`
  (see `backend/.env.example`), or the API will reject every browser request.
