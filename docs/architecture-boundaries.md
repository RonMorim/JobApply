# Architecture Boundaries

**Status:** Living document — JOB-6 deliverable (FastAPI↔Streamlit boundary + multi-tenant preparation notes).
**Scope:** Documentation only. No behavior change. Companion to `CLAUDE.md`, which remains the canonical
quick-reference; this doc goes one level deeper on the two boundaries JOB-6 asked to have made explicit.

---

## 1. FastAPI ↔ Streamlit boundary

### 1.1 Two separate products in one repo

| | **FastAPI product** (the real app) | **Streamlit app** (legacy/reference) |
|---|---|---|
| Entry point | `backend/main.py` (`uvicorn backend.main:app`) | `app.py` (`streamlit run app.py`) |
| Consumers | `web_dashboard/` (Next.js) via REST | A local browser tab, single operator |
| Auth | Supabase JWT (RS256/JWKS or HS256), per-request `CurrentUser` | None — assumes a single local user |
| Data store | `backend/jobs.db` via `backend/services/db.py` (SQLAlchemy) | In-memory / whatever `orchestrator.py` builds per run |
| Status | Actively developed | Frozen — kept for reference only, not on any deploy path |

### 1.2 Dependency direction is one-way

```
app.py  ──imports──▶  orchestrator.py
   │                        │
   └──imports──▶  backend/logic/verifier.py
   └──imports──▶  backend/logic/outreach_engine.py
   └──imports──▶  backend/integrations/job_scraper.py  ◀── also imported by
                                                              backend/scrapers/linkedin_scraper.py
                                                              (FastAPI product)
```

Verified by grep across `backend/`: **nothing in the FastAPI product imports `backend/logic/*`, `app.py`,
or `orchestrator.py`.** The dependency arrow points only from the legacy app into shared/legacy code, never
back. This is the boundary that matters — it means `backend/logic/` and `app.py`/`orchestrator.py` can be
deleted at any time without touching the FastAPI product, but the FastAPI product cannot be simplified by
touching them (they're not on its call path at all).

One module is a genuine, intentional exception: **`backend/integrations/job_scraper.py`** is imported by
both `app.py` (legacy) and `backend/scrapers/linkedin_scraper.py` (FastAPI product). It's shared
low-level HTTP/parsing utility code, not orchestration logic — treat it as product code, not legacy, when
editing it.

### 1.3 What's actually legacy-only

- `app.py` — Streamlit dashboard.
- `orchestrator.py` — defines `analyze_fit()` and a hardcoded `_TARGET_JOB`; only caller is `app.py`.
- `backend/logic/verifier.py`, `backend/logic/outreach_engine.py` — only imported by `app.py` /
  `orchestrator.py`.
- `smoke_test.py` (repo root) — a standalone manual smoke script against `MatchingEngineAgent`, not part of
  either app's runtime and not wired into CI. Keep or delete independently of this boundary; it doesn't
  affect either product.

### 1.4 Cleanup already done / still open

- Legacy build artifacts, mock data, and design references (`backups/legacy_html_designs/`,
  `design-reference.html`, `skills_report.md`, stray PDFs/zips) were removed in the JOB-6 config-hardening
  pass (`eb26e9c`).
- Root `jobs.db` (0-byte stray, untracked, already covered by `*.db` in `.gitignore`) and
  `web_dashboard/job-apply-web/` (a `.next` build-cache leftover, untracked, already covered by `.next/` in
  `.gitignore`) were deleted from the local working tree as part of this pass. Both were already excluded
  from git — there is nothing to commit for their removal, they just shouldn't accumulate on disk.
- **Not done, and out of JOB-6's stated scope:** actually deleting `app.py` / `orchestrator.py` /
  `backend/logic/*` / `backend/integrations/oauth_integrations.py` (the last of these appears unused by any
  route — grep found zero importers outside itself). That's a product decision (is the Streamlit app still
  wanted as a reference tool?), not a refactor call — flagging here rather than deleting unilaterally.

---

## 2. Multi-tenant preparation notes

JOB-6 scope is **foundations only** — no tenant_id column, no tenant-injection middleware, no migration.
This section documents where the system already scopes by identity today and exactly what would need to
change to add a `tenant_id` layer on top of it later.

### 2.1 Current identity model

Every authenticated request resolves to a `CurrentUser` (`backend/api/deps.py`) carrying a single
`user_id: str`, sourced from the verified JWT's `sub` claim. There is no concept of an organization,
workspace, or tenant above the user today — `user_id` is the only scoping key in the system. In practice
`user_id` frequently defaults to the literal string `"default"` in single-user/dev contexts (e.g.
`app_store.get_all(user_id: str = "default")`), which is fine for the current single-tenant deployment but
is the first thing that would need to become "required, no default" once real multi-tenancy lands.

### 2.2 Table-by-table scoping audit

Of the 14 tables in `backend/services/db.py`, **12 already carry a `user_id` column** (most already
indexed): `jobs`, `profile_interviews`, `applications`, `recruiter_reply_drafts`, `master_profiles`,
`profile_entities`, `evidence_records`, `shadow_match_scores`, `ariel_sessions`, `conversation_events`,
`confidence_audit_log`, `ariel_gap_queue`. Every query against these already filters by `user_id` at the
ORM/SQL layer (verified by grep — no query reads across all users' rows). This is the right shape for
tenant scoping to slot into later: **the future migration is "add `tenant_id`, then compose it with the
existing `user_id` filter everywhere," not "add scoping from scratch."**

Two tables intentionally have no `user_id`, and that's correct as of today, not a gap:

- **`kv_store`** — process-level operational flags (scraper pause state, cookie status, OAuth code
  exchange). This is infrastructure state, not user data. It should very likely stay global even under
  multi-tenancy, unless a future requirement makes per-tenant scraper pause/resume a real feature.
- **`company_intel`** — a shared cache of company-level research (industry, culture signals, etc.) that is
  the same regardless of which user asked for it. Under multi-tenancy this is a genuine judgment call worth
  revisiting: keep it a single shared cache across all tenants (cheaper, and company facts don't vary by
  tenant), or scope it per-tenant if tenants should never see each other's research history for audit/
  privacy reasons. No code change needed now — just flagging the decision point.

### 2.3 What a future `tenant_id` migration would touch

1. **Schema:** add `tenant_id` (nullable during migration, backfilled, then `NOT NULL`) to the 12 tables
   listed above, following the exact `_migrate()` pattern already used in `backend/services/db.py`
   (`ALTER TABLE ... ADD COLUMN`, then `CREATE INDEX IF NOT EXISTS` on `(tenant_id, user_id)` composites —
   the JOB-6 indexing pass already established this pattern for `(user_id, status)` etc., so a tenant
   column composes naturally alongside it).
2. **Auth:** `CurrentUser` (`backend/api/deps.py`) would need a `tenant_id` field resolved from the JWT
   (e.g. a custom claim or an org-membership lookup), the same way `user_id` is resolved from `sub` today.
3. **Query layer:** every `session.query(...).filter(X.user_id == user_id)` call in `job_store.py`,
   `app_store.py`, `confidence_matrix_service.py`, and the `crm`/`applications` routes would add
   `.filter(X.tenant_id == tenant_id)` alongside the existing `user_id` filter. Because every one of these
   call sites already takes `user_id` as an explicit parameter (never resolves it from a global/module-level
   variable — this was already an explicit invariant called out in `match_score_service.py`'s docstrings),
   adding a second explicit `tenant_id` parameter through the same call chains is mechanical, not a
   redesign.
4. **Rate limiting / caches** (`backend/api/deps.py`'s in-memory limiter) key on `user_id` today; would need
   `tenant_id` folded into the key if per-tenant (not just per-user) quotas become a requirement.

No code changes were made in this section — it's a map for whoever picks up the actual tenant-injection
work, per JOB-6's "foundations only" scope.
