# Multi-Tenant ERD & Isolation Audit

**Status:** Living document. Companion to `docs/architecture-boundaries.md` §2 (which this supersedes with a
fresh, verified table count — that section's "14 tables, 12 scoped" figure predates `match_triggers`,
`company_intel`, `job_feedback`, `company_culture`, and `ariel_probe_log`, all added since).

**Scope:** `backend/jobs.db` only. Verified against a live copy of the real dev database (18 tables, 656 rows
total) — every finding below was checked against actual code and actual data, not assumed from prior docs.

---

## 1. Table classification

### 1.1 Tenant-scoped (15 tables — carry `user_id`, now also `tenant_id`)

| Table | Owner column(s) | Isolation mechanism |
|---|---|---|
| `jobs` | `user_id` (indexed) | Query filter — see §3 for a caveat |
| `profile_interviews` | `user_id` (indexed) | Query filter |
| `applications` | `user_id` (indexed) | Query filter |
| `recruiter_reply_drafts` | `user_id` (indexed) | Query filter |
| `master_profiles` | `user_id` **(primary key)** | Structural — cannot address another user's row without their exact `user_id` |
| `profile_entities` | `user_id` (indexed) | Query filter |
| `evidence_records` | `user_id` (indexed) | Query filter |
| `shadow_match_scores` | `user_id` (indexed) | Query filter |
| `match_triggers` | `user_id` (indexed), `UNIQUE(user_id, job_id)` | Query filter + uniqueness |
| `job_feedback` | `user_id` (indexed), `UNIQUE(user_id, job_id)` | Query filter + uniqueness |
| `ariel_sessions` | `user_id` (indexed) | Query filter |
| `conversation_events` | `user_id` (indexed) | Query filter |
| `confidence_audit_log` | `user_id` (indexed) | Query filter |
| `ariel_gap_queue` | `user_id` (indexed) | Query filter |
| `ariel_probe_log` | `user_id` (indexed) | Query filter (raw-DDL table, no ORM class) |

### 1.2 Global / shared (3 tables — correctly carry no `user_id`)

| Table | Why it's global |
|---|---|
| `kv_store` | Process-level operational flags (scraper pause state, OAuth code exchange) — infrastructure state, not user data. |
| `company_intel` | Cached company research (financial vibe, tech stack). Identical regardless of which user asked. |
| `company_culture` | Cached culture-fit profile per company. Identical regardless of which user asked. |

These three should **not** gain `tenant_id` without a deliberate product decision — see §5.

---

## 2. Isolation verification (this session, against real code + real data)

| Check | Method | Result |
|---|---|---|
| Every `jobs`/`applications` query call site filters by `user_id` | Read `job_store.py` line-by-line | ✅ All read/write paths filter, **except** dedup-matching queries — see §3 |
| Master Profile cannot be read/written cross-account | Read `master_profile_service.py` + `api/routes/profile.py` | ✅ `user_id` is the table's primary key; every route sources it from `Depends(get_current_user)` (verified JWT `sub` claim), never from client-supplied request data |
| `user_id` is never resolved from a global/module-level variable | Confirmed via `docs/architecture-boundaries.md` §2.1 claim, spot-checked in `master_profile_service.py` and `job_store.py` | ✅ Every service function takes `user_id` as an explicit parameter |
| Migration preserves all existing data | Ran `_migrate_tenant_id()` against a full copy of the real `backend/jobs.db` (656 rows across 18 tables) | ✅ Row counts identical before/after; `tenant_id == user_id` for 100% of backfilled rows |
| Migration is idempotent | Ran twice in sequence against the same DB | ✅ No error, no duplicate columns/indexes |
| Rollback is safe and reversible | Ran migrate → rollback → re-migrate | ✅ Column + indexes cleanly removed and re-added; data untouched throughout |

---

## 3. ⚠️ Found: a real cross-tenant risk in `jobs`, unrelated to the `user_id`/`tenant_id` columns themselves

`job_store.save_with_source_priority()` dedups incoming scraped postings by `apply_url`, `dedup_key`, or
`(title, company)` **across all users** (by design — job postings are the same physical listing regardless
of who scraped them). When a dedup match is found and the incoming source has strictly higher priority
(e.g. `linkedin` → `company_site`), `_upgrade_source_fields()` executes:

```python
if job.user_id:
    row.user_id = job.user_id
```

**This reassigns the existing row's `user_id` to the new scraper run's user.** Because `jobs.job_id` is a
single primary key (not composite with `user_id` — it's derived from the posting URL, not the viewer), one
row currently serves as *both* the shared posting metadata (title, JD text, apply_url) *and* one specific
user's private state (`status`, `match_score`, `applied`, `saved`, `why_ron`, `culture_delta`, `tailored_cv`).

**Concrete failure:** User A's pipeline scrapes a posting via LinkedIn first (row created, `user_id='A'`,
User A saves it and generates a tailored CV). Later, User B's pipeline discovers the same posting via the
company's own career page (`company_site`, higher priority). The upgrade fires, `row.user_id` becomes `'B'`.
The row silently disappears from User A's feed — their saved status, applied flag, and tailored CV are still
in the row, but now attributed to and visible only to User B, who never created them.

**Why this migration doesn't fix it:** adding `tenant_id` (or even a hypothetical `tenant_id` filter at every
query call site) does nothing here — the bug is that `save_with_source_priority` intentionally reassigns
ownership on a dedup match, which is a data-*model* problem (one row, two concerns), not a missing-filter
problem. The real fix is splitting `jobs` into a shared posting table + a per-user state table, which is a
genuinely separate, larger piece of work — **explicitly out of scope for this migration** (it would be new
structural/scoring-adjacent logic, and the brief's constraints rule that out). Flagging here as a known,
verified risk for a dedicated follow-up.

**How common in practice:** narrower than "any duplicate scrape by another user" — it only fires when a
*strictly higher-priority* source discovers the same posting for a *different* user than the one who owns
the existing lower-priority-sourced row. Still real, still worth a follow-up ticket.

---

## 4. ⚠️ Found: a pre-existing, unrelated fresh-install bug (not introduced by this migration, not fixed by it)

Running `init_db()` against a genuinely empty SQLite file crashes in `_migrate_confidence_matrix()`:

```
sqlite3.OperationalError: table evidence_records has 11 columns but 12 values were supplied
```

Confirmed via `git stash` to reproduce identically against the **unmodified** `db.py` — this predates any
change in this migration. Root cause: `EvidenceRecordRow`'s ORM column list (12 columns, including
`is_ai_assisted`) has drifted from the raw `_EVIDENCE_RECORDS_DDL` string (11 columns) used by the
rename/recreate migration dance for `evidence_records`. On a fresh DB, `Base.metadata.create_all()` creates
the table via the ORM's 12-column definition; the subsequent migration then tries to copy that 12-column
table into an 11-column recreation and fails on the column-count mismatch.

**Why it's never been hit:** the real dev `jobs.db` was created years ago and has only ever been
incrementally `ALTER`'d forward — nobody has run `init_db()` against a truly empty file. This migration's
own tests deliberately avoided tripping this landmine by testing `_migrate_tenant_id()` directly against a
copy of the real, already-migrated dev DB rather than a from-scratch `init_db()` call.

**Not fixed here** — unrelated to tenant scoping, and fixing `_EVIDENCE_RECORDS_DDL`/ORM drift safely needs
its own dedicated review (touches an append-only evidence ledger). Worth a follow-up ticket; low urgency
since it only affects a from-scratch fresh install, which doesn't currently happen in this project's
lifecycle.

---

## 5. What `tenant_id` does and does NOT do

**Does:** every tenant-scoped table now has a nullable `tenant_id TEXT` column, indexed, backfilled from
that row's own `user_id` (one account = one tenant, today — not a shared literal like `'default'`, which
would have made the column meaningless). This is the schema half of the brief's "forward-compatible
`tenant_id` column" requirement.

**Does NOT:** get consumed by any query filter yet. There is no tenant concept above `user_id` in
`CurrentUser` (`backend/api/deps.py`) — no JWT claim, no org/workspace table, nothing to resolve a real
`tenant_id` from at request time. Wiring `tenant_id` into every `WHERE` clause today would mean filtering by
a column whose value is identical to `user_id` everywhere — a no-op that adds risk (a second column to keep
in sync) without any real isolation benefit. This matches `docs/architecture-boundaries.md` §2.3's own
conclusion and this brief's explicit framing of `tenant_id` as "forward-compatible," not "must be enforced
now." When an org/workspace concept lands, query-layer filtering composes mechanically alongside the
existing `user_id` filter — every call site already takes `user_id` as an explicit parameter, never a global.

---

## 6. Entity-relationship diagram

```mermaid
erDiagram
    MASTER_PROFILES ||--o{ JOBS : "owns (user_id)"
    MASTER_PROFILES ||--o{ APPLICATIONS : "owns (user_id)"
    MASTER_PROFILES ||--o{ PROFILE_INTERVIEWS : "owns (user_id)"
    MASTER_PROFILES ||--o{ RECRUITER_REPLY_DRAFTS : "owns (user_id)"
    MASTER_PROFILES ||--o{ PROFILE_ENTITIES : "owns (user_id)"
    MASTER_PROFILES ||--o{ SHADOW_MATCH_SCORES : "owns (user_id)"
    MASTER_PROFILES ||--o{ MATCH_TRIGGERS : "owns (user_id)"
    MASTER_PROFILES ||--o{ JOB_FEEDBACK : "owns (user_id)"
    MASTER_PROFILES ||--o{ ARIEL_SESSIONS : "owns (user_id)"
    MASTER_PROFILES ||--o{ ARIEL_GAP_QUEUE : "owns (user_id)"
    MASTER_PROFILES ||--o{ ARIEL_PROBE_LOG : "owns (user_id)"

    PROFILE_ENTITIES ||--o{ EVIDENCE_RECORDS : "entity_id"
    PROFILE_ENTITIES ||--o{ CONFIDENCE_AUDIT_LOG : "entity_id"
    ARIEL_SESSIONS ||--o{ CONVERSATION_EVENTS : "session_id"
    ARIEL_SESSIONS ||--o{ EVIDENCE_RECORDS : "session_id (optional)"

    JOBS ||--o| APPLICATIONS : "job_id (loosely linked, not FK-enforced)"
    JOBS ||--o| MATCH_TRIGGERS : "job_id"
    JOBS ||--o| JOB_FEEDBACK : "job_id"
    JOBS ||--o| RECRUITER_REPLY_DRAFTS : "job_id"

    MASTER_PROFILES {
        string user_id PK
        string tenant_id "nullable, = user_id today"
        string email
        string onboarding_status
        json master_profile
        bool is_admin
    }
    JOBS {
        string job_id PK "derived from posting URL — NOT composite with user_id, see section 3"
        string user_id "indexed"
        string tenant_id "nullable, indexed"
        float match_score
        string status
        json tailored_cv
    }
    APPLICATIONS {
        string application_id PK
        string user_id "indexed"
        string tenant_id "nullable, indexed"
        string job_id "indexed, not FK-enforced"
        string status
    }
    PROFILE_ENTITIES {
        string entity_id PK
        string user_id "indexed"
        string tenant_id "nullable, indexed"
        float confidence_score
        string verification_level
    }
    EVIDENCE_RECORDS {
        string evidence_id PK
        string entity_id "indexed"
        string user_id "indexed"
        string tenant_id "nullable, indexed"
        string source_type
    }

    KV_STORE {
        string key PK
        string value
        note "GLOBAL — no user_id/tenant_id, by design"
    }
    COMPANY_INTEL {
        string company_key PK
        json profile_json
        note "GLOBAL — shared cache across all tenants"
    }
    COMPANY_CULTURE {
        string company_key PK
        json profile_json
        note "GLOBAL — shared cache across all tenants"
    }
```

*(`job_id`/`entity_id`/`session_id` cross-table links above are application-level relationships, not
SQLite `FOREIGN KEY` constraints — this codebase does not currently enforce referential integrity at the DB
level for these; string columns compared at the ORM/query layer. Adding real FKs is a separate, larger
change than this migration's scope — SQLite FKs are also off by default (`PRAGMA foreign_keys`) and only
selectively turned on in this file's `evidence_records` rename/recreate migrations.)*

---

## 7. Migration inventory

| Change | Where | Type |
|---|---|---|
| `tenant_id` column on 14 ORM-mapped tenant tables | `backend/services/db.py` — each model class | Additive, nullable |
| `tenant_id` column on `ariel_probe_log` (raw-DDL table) | `backend/services/db.py::_migrate_tenant_id()` | Additive, nullable |
| Backfill `tenant_id = user_id` | `_migrate_tenant_id()` | Idempotent, only touches `NULL` rows |
| `ix_<table>_tenant_id` on all 15 tables | `_migrate_tenant_id()` | New index |
| `ix_jobs_tenant_user`, `ix_applications_tenant_user` composites | `_migrate_tenant_id()` | New index, mirrors existing `(user_id, status)` pattern |
| `TENANT_SCOPED_TABLES` / `GLOBAL_TABLES` constants | `backend/services/db.py` | New — single source of truth for future audits/tests |
| `_rollback_tenant_id()` | `backend/services/db.py` | New — manual escape hatch, never auto-invoked |
| `backend/tests/test_tenant_isolation.py` | New file | Automated isolation proof |
