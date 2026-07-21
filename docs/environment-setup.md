# Environment Setup

**Status:** Living document. Companion to `CLAUDE.md` (quick reference) and `docs/architecture-boundaries.md`
(FastAPI↔Streamlit boundary + multi-tenant notes). This doc is the from-clean-state setup reference and the
place environment-specific gotchas get recorded once found.

This project has **three independently-managed dependency sets** — mixing them up (installing the wrong
`requirements.txt`, or skipping the dev one) is the single most common way a local environment silently
diverges from CI. Know which one you need before you start.

---

## 1. Dependency inventory

| Set | File | Installs | Used by |
|---|---|---|---|
| Backend (product) | `backend/requirements.txt` | FastAPI, SQLAlchemy, Anthropic SDK, Playwright, aiohttp, pandas, etc. | The real app (`uvicorn backend.main:app`) |
| Backend (test/dev) | `backend/requirements-dev.txt` | `-r requirements.txt` **+** `pytest==8.3.4`, `pytest-asyncio==0.23.5` | Running `backend/tests/` locally and in CI |
| Frontend | `web_dashboard/package.json` | Next.js 14, React, Tailwind, Supabase JS, Zod, etc. | `web_dashboard/` (Next.js app router) |

There is **no root-level `pyproject.toml`** — dependency management is `requirements.txt`-based throughout.

**A fourth file, root `requirements.txt`, is legacy** — it's the dependency set for the standalone Streamlit
app (`app.py` / `orchestrator.py`), not the FastAPI product. See `docs/architecture-boundaries.md` §1 for the
full legacy/active boundary. If you're working on the actual product (the thing `web_dashboard/` talks to),
you want `backend/requirements*.txt`, not this one.

### `backend/requirements-dev.txt` — mandatory for running tests

```
-r requirements.txt
pytest==8.3.4
pytest-asyncio==0.23.5
```

`pytest-asyncio` is **not optional**: `backend/pytest.ini` sets `asyncio_mode = auto`, so every
`@pytest.mark.asyncio` test requires the plugin to even collect correctly. Without it, those tests don't
skip — they fail with `Failed: async def functions are not natively supported` / an "Unknown pytest.mark.asyncio"
warning, which looks like a broken test rather than a missing dependency. This has already caused confusion
once in this project's history (a session ran `pytest` against a venv built from `requirements.txt` alone —
the correct dependency was already declared in `requirements-dev.txt`, just never installed).

---

## 2. Setup from a clean state

### 2.1 Core Development (run the app)

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in ANTHROPIC_API_KEY at minimum — see .env.example for the full list
cd ..
uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd web_dashboard
npm install
npm run dev
```

This is sufficient to run and manually exercise the product. It is **not** sufficient to run the backend
test suite — `pytest`/`pytest-asyncio` aren't in this dependency set on purpose (test tooling shouldn't ship
in a production install).

### 2.2 Test Suite Execution (run `backend/tests/`)

```bash
cd backend
source .venv/bin/activate        # reuse the same venv as Core Development — do not create a second one
pip install -r requirements-dev.txt
cd ..
pytest backend/tests -q
```

`requirements-dev.txt` installs `requirements.txt` too (via `-r`), so you do not need to run both install
commands — `pip install -r requirements-dev.txt` alone is enough for a venv that will run tests. Only skip
straight to `requirements.txt` alone if you specifically want a test-tooling-free environment (e.g.
mirroring a production install).

Frontend has no test framework configured — `npm run lint` and `npx tsc --noEmit` (from `web_dashboard/`)
are the available checks.

### 2.3 "Ready to test" — the exact commands

```bash
cd backend
python3 -m venv .venv                    # skip if a venv already exists
source .venv/bin/activate
pip install -r requirements-dev.txt
cd ..
ANTHROPIC_API_KEY=test-key pytest backend/tests -q   # matches the CI env exactly
```

---

## 3. Known Issues

### 3.1 `evidence_records` raw-DDL vs. ORM drift in `init_db()` — RESOLVED

This section previously warned that `init_db()` (`backend/services/db.py`) crashed against a genuinely
empty SQLite file with `sqlite3.OperationalError: table evidence_records has 11 columns but 12 values were
supplied`, because `_EVIDENCE_RECORDS_DDL` (the raw-SQL migration path) had drifted out of sync with
`EvidenceRecordRow`'s ORM column list (missing `is_ai_assisted`).

**No longer reproduces.** `_EVIDENCE_RECORDS_DDL` now includes `is_ai_assisted INTEGER NOT NULL DEFAULT 0`,
matching the ORM definition column-for-column. Re-verified directly (2026-07-16, during the
`refactor/llm-wrapper-v2` Docker setup work) by pointing `db_module.ENGINE` at a brand-new, previously
nonexistent SQLite file and calling `init_db()` twice in a row (idempotency check) — both calls succeeded
with no error, and the full `test_profile_trust.py` / `test_tenant_isolation.py` suites still pass.

A genuinely fresh clone (or a fresh Docker container — see `docs/docker-setup.md`) can safely let
`init_db()` create `backend/jobs.db` from nothing; no seed file or workaround is needed.

### 3.2 `backend/pytest.ini` sets an option the pinned `pytest-asyncio` doesn't recognize

```
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

`asyncio_default_fixture_loop_scope` was introduced in a later `pytest-asyncio` release than the pinned
`0.23.5`; installing exactly what `requirements-dev.txt` declares produces one harmless
`PytestConfigWarning: Unknown config option` on every run. Doesn't fail anything — flagging so it isn't
mistaken for a new problem. A `pytest-asyncio` version bump would clear it; not done here since bumping a
CI-pinned test dependency is a deliberate call for whoever owns CI, not a side effect of an environment-docs
pass.

### 3.3 Two unused, near-empty virtualenvs at the repo root

`.venv/` and `venv/` both exist at the project root (outside `backend/`), both Python 3.9.6, both missing
the packages root `requirements.txt` declares (`.venv` has a stray manually-installed `anthropic`; `venv` has
essentially nothing). Neither is `backend/.venv` (the one actually used to run the product/tests) or
`web_dashboard/node_modules` (frontend). Both are gitignored, so they aren't a repo-hygiene problem in the
strict sense, but they're dead local disk space and a plausible source of "which venv am I in" confusion for
a new developer working on the legacy Streamlit app. Not deleted here — removing a directory that might be
someone's active shell environment isn't a call to make unilaterally in a docs pass. Recommendation: whoever
still uses the legacy `app.py` should pick one, delete the other, and record which one in this file.

### 3.4 Root `.env` — legacy, and contains live secrets

Root-level `.env` (gitignored, never committed — confirmed via `git log --all -- .env`) is the legacy
Streamlit app's env file. The active product reads `backend/.env`, not this one (see `CLAUDE.md`). It
currently holds live API key values in plaintext, which is expected for a local `.env` but worth flagging
explicitly: don't `cat` it into a shared terminal, screen-share, or paste it into an issue/PR. No action
taken on the file itself here.
