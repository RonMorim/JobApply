# JobApply

AI-driven, ATS-optimized job-application platform. Backend is FastAPI (Python); frontend is Next.js.
Four core B2C features: Master Profile, Match Score (0-100% JD match), Template Engine (ATS-safe resume
templates), Live Editor (manual CV editing before PDF export).

Full architectural context lives in [`CLAUDE.md`](CLAUDE.md) — read that first if you're new here. This
file covers getting a local environment running.

> **Legacy note:** root `app.py`/`orchestrator.py` are a frozen Streamlit reference app, not the product —
> see [`docs/architecture-boundaries.md`](docs/architecture-boundaries.md) §1. Everything below is for the
> actual product: `backend/` (FastAPI) + `web_dashboard/` (Next.js).

---

## Quick start

### Core Development

Run this to get the app itself running and manually testable. Does **not** install test tooling.

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in ANTHROPIC_API_KEY at minimum
cd .. && uvicorn backend.main:app --reload

# Frontend — separate terminal
cd web_dashboard
npm install && npm run dev
```

### Test Suite Execution

Run this (in addition to, or instead of, the backend step above) to run `backend/tests/`. Uses a
**different, dev-only dependency file** — `pytest`/`pytest-asyncio` are deliberately excluded from the
production `requirements.txt`.

```bash
cd backend
source .venv/bin/activate    # same venv as above — don't create a second one
pip install -r requirements-dev.txt
cd .. && pytest backend/tests -q
```

`pytest-asyncio` is **mandatory**, not optional, for this to work: `backend/pytest.ini` sets
`asyncio_mode = auto`, so async tests fail outright (not skip) without it. If you ever see
`Unknown pytest.mark.asyncio` warnings alongside test failures, this is almost certainly the cause — you
installed `requirements.txt` instead of `requirements-dev.txt`.

Frontend has no test framework configured; `npm run lint` and `npx tsc --noEmit` (from `web_dashboard/`) are
the available checks.

**Full dependency inventory, from-clean-state commands, and known environment issues:**
see [`docs/environment-setup.md`](docs/environment-setup.md).

---

## Documentation map

| Doc | Covers |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Architecture, commands, mandatory AI scoring principles — start here |
| [`docs/environment-setup.md`](docs/environment-setup.md) | Full dependency inventory, setup from clean state, Known Issues |
| [`docs/architecture-boundaries.md`](docs/architecture-boundaries.md) | FastAPI↔Streamlit legacy boundary, multi-tenant scoping notes |
| [`docs/multi-tenant-erd.md`](docs/multi-tenant-erd.md) | Database ERD, tenant-scoping classification, migration details |
| [`DESIGN_SYSTEM_V2.md`](DESIGN_SYSTEM_V2.md) | "Meridian" design system (current) |
