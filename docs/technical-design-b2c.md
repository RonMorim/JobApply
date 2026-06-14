# Technical Design Document: B2C Upgrade
**Project:** JobApply_Venture  
**Version:** 1.0  
**Date:** 2026-05-08  
**Author:** Lead System Architect  
**Source PRD:** `docs/prd-b2c.md`  
**Status:** Approved for Implementation

---

## Table of Contents
1. [Architecture Audit — What Already Exists](#1-architecture-audit--what-already-exists)
2. [Data Flow Overview](#2-data-flow-overview)
3. [Feature 1 — Master Profile](#3-feature-1--master-profile)
4. [Feature 2 — Match Score](#4-feature-2--match-score)
5. [Feature 3 — Template Engine](#5-feature-3--template-engine)
6. [Feature 4 — Live Editor](#6-feature-4--live-editor)
7. [API Contract — Full Endpoint Inventory](#7-api-contract--full-endpoint-inventory)
8. [Module Change Map](#8-module-change-map)
9. [Non-Breaking Guarantees](#9-non-breaking-guarantees)
10. [Implementation Order](#10-implementation-order)

---

## 1. Architecture Audit — What Already Exists

Before prescribing new work, this section maps each PRD feature to the existing codebase. Implementing over this without understanding what is already live will cause duplication or regression.

### 1.1 Existing Modules Relevant to B2C

| File | Purpose | B2C Relevance |
|---|---|---|
| `backend/agents/tailor.py` | TailorAgent — LLM CV generation | Central pipeline; Match Score runs after it |
| `backend/services/user_profile.py` | In-memory `USER_PROFILE` dict; phone/location persistence via `personal_overrides.json` | Source of contact data for all PDF renders |
| `backend/services/supplemental_store.py` | Stores supplemental Q&A to `backend/supplemental_answers.json`; injected into `build_full_text()` | **Partial Master Profile implementation** — see §3.2 |
| `backend/services/pdf_builder.py` | Playwright/Chromium PDF renderer; already has `TEMPLATE_REGISTRY`, `_TEMPLATE_MAP`, `build_pdf(cv_data, template_id)` | **Template Engine already wired** |
| `backend/services/match_score_service.py` | Phase 1 Python scoring + Phase 2 Haiku LLM validation | **Match Score already implemented** |
| `backend/api/routes/resumes.py` | FastAPI router; all five B2C endpoints already present | **All new API endpoints already exist** |
| `backend/engines/master_profile.py` | MasterProfile class for bullet-improvement placeholder tokens; writes to `data/user_master_profile.json` | **Different concern** — do NOT extend for B2C |
| `backend/services/profile_manager.py` | Unclear — must audit before touching | Read before any modification |
| `web_dashboard/src/components/ApplierPreview.tsx` | Main CV preview modal; fully wired to B2C components | Integration complete |
| `web_dashboard/src/components/MatchScorePanel.tsx` | CircleGauge + sub-bars + keyword chips | Built |
| `web_dashboard/src/components/TemplateSelectorBar.tsx` | SVG thumbnail template selector | Built |
| `web_dashboard/src/components/LiveEditor.tsx` | Inline structured CV editor | Built |

### 1.2 B2C Feature Implementation Status

| Feature | Backend | Frontend | Status |
|---|---|---|---|
| Master Profile (structured) | `supplemental_store.py` covers flat Q&A only; **no** personal/metrics/role_preferences schema | N/A (P1 UI deferred) | **Gap: new service needed** |
| Match Score | `match_score_service.py` — Phase 1 + Phase 2 complete | `MatchScorePanel.tsx` complete | Done |
| Template Engine | `pdf_builder.py` — 3 templates, registry, routing | `TemplateSelectorBar.tsx` complete | Done |
| Live Editor | Stateless — no dedicated backend; uses `/render-pdf` and `/match-score` | `LiveEditor.tsx` + `ApplierPreview.tsx` wired | Done |

**Net new backend work required:** Only the Master Profile structured service. Everything else is already implemented.

---

## 2. Data Flow Overview

### 2.1 End-to-End: CV Generation with All B2C Features

```
User clicks "Generate CV"
        |
        v
POST /api/resumes/tailor
  {job_id, supplemental_answers}
        |
        +--- [1] MasterProfileService.resolve_answers(missing_requests)
        |         Reads data/master_profile.json
        |         Returns cached answers -> skip user prompts
        |
        +--- [2] TailorAgent.tailor(job, supplemental_answers)
        |         Reads USER_PROFILE (user_profile.py)
        |         Reads supplemental_answers.json (supplemental_store.py)
        |         Calls Claude Sonnet -> cv_data dict or missing_data
        |
        +--- (if missing_data) -> return {status: "missing_data", requests: [...]}
        |         Frontend shows MissingDataForm
        |         User answers -> POST /tailor again with supplemental_answers
        |         MasterProfileService.merge_answers() -> data/master_profile.json
        |
        +--- [3] build_pdf(cv_data, template_id="t2_modern")
        |         Renders t2_modern.html with cv_data via Playwright
        |         Returns raw PDF bytes -> base64
        |
        +--- [4] compute_match_score_async(cv_data, jd_proxy, run_llm_validation=True)
        |         Phase 1: Python keyword/skills/seniority (<100ms)
        |         Phase 2: Claude Haiku validation (~1-2s)
        |         Returns MatchScoreResult
        |
        +--- return TailorResponse {
               status: "ok",
               cv_data, pdf_b64,
               match_score: MatchScoreResult.as_dict(),
               preferred_template: "t2_modern"
             }
```

### 2.2 Live Editor Flow (No LLM)

```
User edits CV in LiveEditor component
        |
User clicks Save
        |
        +--- POST /api/resumes/match-score
        |    {job_id, cv_data=editedCvData, llm_validation=false}
        |    -> Phase 1 only (<100ms) -> updated MatchScoreResult
        |
        +--- POST /api/resumes/render-pdf
             {cv_data=editedCvData, template_id=selectedTemplate}
             -> build_pdf() -> new PDF bytes -> base64

Both fire in Promise.all() — parallel, no LLM call, ~200-500ms total
```

### 2.3 Template Switch Flow

```
User clicks template thumbnail (TemplateSelectorBar)
        |
        +--- POST /api/resumes/render-pdf
             {cv_data=editedCvData ?? cvState.cvData, template_id=newTemplateId}
             -> build_pdf(cv_data, template_id) -> PDF bytes
             -> setCvState.pdfB64 -> iframe re-renders
```

### 2.4 Master Profile Data Flow

```
supplemental_answers.json          master_profile.json
(flat [{id, answer}] list)         (structured B2C schema)
          |                                 |
          |  supplemental_store.get_as_text()    |  MasterProfileService.load()
          +--------------+-----------------------+
                         |
                    build_full_text()
                    (user_profile.py)
                         |
                         v
                   TailorAgent prompt
                   (PREVIOUSLY_ANSWERED_QUESTIONS block)
```

**Key insight:** `supplemental_store.py` feeds the LLM's context window so answered questions aren't re-asked. `master_profile.json` (new) is the structured backing store that enables answer lookup *before* reaching the LLM.

---

## 3. Feature 1 — Master Profile

### 3.1 The Gap Between PRD and Current Implementation

The PRD specifies a structured JSON store at `data/master_profile.json` with three top-level sections: `personal`, `metrics`, and `role_preferences`. The current system has:

- `backend/supplemental_answers.json` — flat `[{id, answer}]` list, no structure, no confidence scoring, no personal or role_preferences sections.
- `personal_overrides.json` — stores only `phone` and `location`.

The new `master_profile_service.py` must bridge these: read from both, write to the structured schema, and expose the lookup API the tailor route needs.

**Critical naming constraint:** Do NOT modify or extend `backend/engines/master_profile.py`. That class (`MasterProfile`) is a completely different concern — it manages CV bullet improvement placeholder tokens (e.g., `[X%]`, `[N]`). The new B2C service lives at `backend/services/master_profile_service.py`.

### 3.2 File Schema — `data/master_profile.json`

```json
{
  "version": 1,
  "last_updated": "2026-05-08T14:30:00",
  "personal": {
    "full_name":    "Ron Morim",
    "email":        "ronmorim98@gmail.com",
    "phone":        "",
    "linkedin_url": "linkedin.com/in/ronmorim",
    "location":     ""
  },
  "metrics": {
    "<question_id_slug>": {
      "value":      "User's answer as a string",
      "source":     "supplemental",
      "confidence": "high",
      "created_at": "2026-05-08T14:30:00",
      "updated_at": "2026-05-08T14:30:00"
    }
  },
  "role_preferences": {
    "target_titles":       ["Product Manager", "Senior PM"],
    "preferred_locations": ["Tel Aviv", "Remote"],
    "work_type":           "hybrid",
    "salary_min_usd":      null
  }
}
```

**Field rules:**
- `version` — must be checked on load; if absent or 0, treat as fresh profile.
- `metrics` keys — use the `question_id` from TailorAgent's `missing_data_requests[].id` (e.g., `"us_client_exp"`, `"crm_tool_used"`). Snake_case slugs defined in the TailorAgent system prompt.
- `confidence` — set to `"low"` if `updated_at` is older than 180 days. Re-used `low`-confidence answers trigger a frontend verification prompt (P2).
- `personal` — mirrors `user_profile.py -> USER_PROFILE["personal"]`. On load, `MasterProfileService` calls `save_personal_field()` to sync phone/location back into the in-memory `USER_PROFILE`.

### 3.3 New Module — `backend/services/master_profile_service.py`

**Responsibility:** Single gateway for all reads and writes to `data/master_profile.json`.

```python
"""
MasterProfileService — B2C structured profile store.

Reads: data/master_profile.json (structured)
Also reads: backend/supplemental_answers.json (flat, for bootstrap migration)
Writes: data/master_profile.json (atomic write via tempfile)

Public API
----------
load() -> dict
save(profile: dict) -> None                    — atomic write
get_cached_answer(question_id) -> str | None
merge_answers(answers: dict[str, str]) -> int  — returns count of new entries written
bootstrap_from_supplemental() -> int           — one-time migration
"""
```

**Key method signatures:**

```python
_DATA_DIR     = Path(__file__).resolve().parents[2] / "data"
_PROFILE_PATH = _DATA_DIR / "master_profile.json"

def load() -> dict:
    """Load profile from disk; return empty scaffold on missing/corrupt file."""

def save(profile: dict) -> None:
    """Atomic write: tempfile -> os.replace -> _PROFILE_PATH."""

def get_cached_answer(question_id: str) -> str | None:
    """
    Return stored answer for question_id, or None.
    MVP: always returns answer regardless of confidence.
    P2: return None for confidence="low" and surface verification prompt.
    """

def merge_answers(answers: dict[str, str]) -> int:
    """
    Write new question_id->answer pairs into profile["metrics"].
    Always updates updated_at for existing entries.
    Sets source="supplemental", confidence="high".
    Also writes answers to supplemental_store (keeps flat store in sync).
    Returns count of newly written entries.
    """

def bootstrap_from_supplemental() -> int:
    """
    One-time migration: import all entries from supplemental_answers.json
    into master_profile.json["metrics"], skipping already-present keys.
    Idempotent — safe to call on every app startup.
    Returns count of entries imported.
    """
```

**Atomic write pattern:**
```python
import os, tempfile, json
from pathlib import Path

def save(profile: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_DATA_DIR, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PROFILE_PATH)
    except Exception:
        os.unlink(tmp)
        raise
```

### 3.4 Integration Points

#### 3.4.1 Tailor Route — Answer Auto-Fill (P0)

Add to `POST /tailor` in `resumes.py`. After the first `agent.tailor()` call returns `missing_data`, check the profile for cached answers and re-run automatically if any hits are found:

```python
from backend.services.master_profile_service import get_cached_answer, merge_answers

# After result = await agent.tailor(job, supplemental_answers=jd_answers or None):
if result["type"] == "missing_data":
    requests = result.get("requests", [])
    auto_filled: dict[str, str] = {}
    unanswered = []
    for req in requests:
        cached = get_cached_answer(req["id"])
        if cached:
            auto_filled[req["id"]] = cached
        else:
            unanswered.append(req)

    if auto_filled:
        # Re-run with auto-filled answers merged in
        combined = {**(jd_answers or {}), **auto_filled}
        result = await agent.tailor(job, supplemental_answers=combined)
        # If still missing_data after auto-fill, only show unanswered questions
        if result["type"] == "missing_data":
            return TailorResponse(
                status="missing_data",
                missing_data_requests=unanswered,
            )
    else:
        return TailorResponse(
            status="missing_data",
            missing_data_requests=requests,
        )
```

#### 3.4.2 Tailor Route — Answer Persistence (P0)

After successful generation, merge answers into the structured profile:

```python
# In /tailor success path, after cv_data confirmed:
if jd_answers:
    try:
        merge_answers(jd_answers)   # writes to master_profile.json + supplemental_answers.json
    except Exception:
        pass  # never block CV output on profile write failure
```

#### 3.4.3 App Startup — Bootstrap (P0)

In `backend/main.py` lifespan:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.services.db import init_db
    from backend.services.master_profile_service import bootstrap_from_supplemental
    init_db()
    try:
        n = bootstrap_from_supplemental()
        if n:
            logger.info("[startup] Bootstrapped %d answers from supplemental store", n)
    except Exception as exc:
        logger.warning("[startup] master_profile bootstrap failed (non-fatal): %s", exc)
    ...
    yield
```

#### 3.4.4 Personal Field Sync on Load

In `master_profile_service.load()`:
```python
def load() -> dict:
    ...
    # Sync phone/location back into USER_PROFILE in memory
    personal = profile.get("personal", {})
    for field in ("phone", "location"):
        value = personal.get(field, "").strip()
        if value:
            try:
                from backend.services.user_profile import save_personal_field
                save_personal_field(field, value)
            except Exception:
                pass
    return profile
```

### 3.5 New API Endpoints (P1 — Profile View/Edit)

New router at `backend/api/routes/profile.py`:

```python
from fastapi import APIRouter
from backend.services.master_profile_service import load, save, merge_answers

router = APIRouter()

@router.get("")
async def get_profile():
    return load()

@router.put("/personal")
async def update_personal(field: str, value: str):
    profile = load()
    if field in ("phone", "location", "linkedin_url"):
        profile["personal"][field] = value.strip()
        save(profile)
        if field in ("phone", "location"):
            from backend.services.user_profile import save_personal_field
            save_personal_field(field, value)
    return {"updated": True}

@router.put("/metrics")
async def update_metric(question_id: str, value: str | None = None):
    profile = load()
    if value is None:
        profile["metrics"].pop(question_id, None)
        save(profile)
        return {"deleted": True}
    profile["metrics"][question_id] = {
        "value": value, "source": "manual",
        "confidence": "high",
        "updated_at": _now_iso(),
    }
    save(profile)
    return {"updated": True}
```

Register in `main.py`:
```python
from backend.api.routes import agents, applications, jobs, resumes, settings, profile
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
```

---

## 4. Feature 2 — Match Score

### 4.1 Implementation Status

**Fully implemented. No new backend work required for MVP.**

| Component | File | Status |
|---|---|---|
| Phase 1 scoring (keyword, skills, seniority) | `backend/services/match_score_service.py` | Done |
| Phase 2 Haiku LLM validation | `backend/services/match_score_service.py` | Done |
| `MatchScoreResult` dataclass + `as_dict()` | `backend/services/match_score_service.py` | Done |
| `POST /api/resumes/match-score` endpoint | `backend/api/routes/resumes.py:388-420` | Done |
| Match score computed and returned from `/tailor` | `backend/api/routes/resumes.py:261-275` | Done |
| `MatchScorePanel` React component | `web_dashboard/src/components/MatchScorePanel.tsx` | Done |
| Wired into `ApplierPreview` | `web_dashboard/src/components/ApplierPreview.tsx` | Done |

### 4.2 JD Proxy Construction — Architectural Decision

`JobMatch` (the stored model) does not persist raw JD text — only structured fields. The proxy function `_build_jd_proxy()` in `resumes.py` constructs a surrogate JD text:

```python
def _build_jd_proxy(job) -> str:
    parts = [f"{job.title} at {job.company}"]
    if job.why_ron:           parts.append(job.why_ron)
    if job.scoring_rationale: parts.append(job.scoring_rationale)
    if job.detailed_analysis and job.detailed_analysis.critical_gaps:
        parts.append("Required: " + ", ".join(job.detailed_analysis.critical_gaps))
    return " ".join(parts)
```

**Consequence:** Score quality degrades for freshly-scraped jobs where `why_ron` and `scoring_rationale` are not yet populated. The frontend should surface a "Limited job data — score may be inaccurate" indicator when the jd_proxy has fewer than 100 characters (P1 task for the frontend).

### 4.3 Scoring Algorithm Reference

```
Total (0-100) = keyword_overlap (0-40) + skills_alignment (0-35) + seniority_alignment (0-25)

keyword_overlap:
  jd_keywords = words appearing >= 2x in jd_proxy + uppercase technical tokens
  score_1 = (|matched_kw| / |jd_keywords|) * 40

skills_alignment:
  jd_skills extracted via 7 regex patterns ("experience with X", "proficient in X", etc.)
  exact match -> 1.0 weight | substring match -> 0.6 | blob mention -> 0.4
  score_2 = (weighted_sum / |jd_skills|) * 35

seniority_alignment:
  bands: intern=1, junior/associate=2, mid/specialist=3, manager/senior=4,
         lead=5, principal/staff=6, head/director=7, vp=8 (default: 3)
  factor: delta=0 -> 1.0, delta=1 -> 0.7, delta=2 -> 0.4, delta>=3 -> 0.1
  score_3 = factor * 25

Phase 2 Haiku adjustment: +-5 pts max, clamped, updates missing_keywords + suggestions
```

### 4.4 Phase 1 vs Phase 2 Call Sites

| Caller | `run_llm_validation` | Latency | Why |
|---|---|---|---|
| `POST /tailor` (first generation) | `True` | ~2-3s added | One-time quality gate per generation |
| `POST /match-score` from Live Editor Save | `False` | <100ms | Instant feedback; no LLM budget for every keystroke |
| `POST /match-score` explicit re-validate (P2) | `True` | ~2s | Persona C power-user feature |

---

## 5. Feature 3 — Template Engine

### 5.1 Implementation Status

**Fully implemented. No new work required.**

| Component | File | Status |
|---|---|---|
| Template HTML files | `backend/templates/cv/t1_classic.html`, `t2_modern.html`, `t3_executive.html` | Done |
| `_TEMPLATE_MAP` + `TEMPLATE_REGISTRY` | `backend/services/pdf_builder.py:40-50` | Done |
| `_resolve_template(template_id)` | `backend/services/pdf_builder.py:53-59` | Done |
| `build_pdf(cv_data, template_id)` | `backend/services/pdf_builder.py:287-312` | Done |
| `GET /api/resumes/templates` | `backend/api/routes/resumes.py:338-341` | Done |
| `POST /api/resumes/render-pdf` | `backend/api/routes/resumes.py:351-364` | Done |
| `TemplateSelectorBar` + SVG thumbnails | `web_dashboard/src/components/TemplateSelectorBar.tsx` | Done |
| `fetchTemplates`, `renderPdf` API client | `web_dashboard/src/lib/api.ts` | Done |

### 5.2 Template-to-HTML Class Contract

All three templates consume the same HTML class names output by `pdf_builder._build_*()`. **Never change a class name in a `_build_*` function without updating all three templates.**

```
Core classes (must exist in all templates):
  .entry-hdr         — flex row: meta left, dates right
  .entry-meta        — column: role/degree + company/institution
  .entry-role        — bold role title
  .entry-company     — company name (muted)
  .entry-dates       — date range (right-aligned)
  .bullets li        — experience bullet
  .edu-entry         — education block
  .edu-degree        — degree title
  .edu-institution   — school name
  .edu-honors        — honours/awards
  .edu-coursework    — relevant coursework
  .skill-cat         — one skill category block
  .skill-cat-label   — category label
  .skill-tag         — individual skill token
  .side-sec          — sidebar section wrapper
  .sec-title         — sidebar section heading
  .lang-row          — language + level row
  .mil-role          — military role
  .mil-unit          — military unit
  .vol-text          — volunteering text block
  .contact-line      — contact header item (phone, location)
```

### 5.3 ATS Safety Checklist (All Templates)

Run before adding any new template to `_TEMPLATE_MAP`:

```
[ ] No <table> used for layout
[ ] No position: absolute or fixed on content blocks
[ ] No column-count > 1 in the stylesheet
[ ] No @import or external font URLs
[ ] All font-family values are system stack only (no Google Fonts)
[ ] No SVG or <img> elements containing readable resume text
[ ] Contact info in plain <p> or <span> tags
[ ] Section headings use <h2> or <h3>, not styled <div>
[ ] Page margins at least 0.5in (~36px at 72dpi)
[ ] Tested in Playwright: page.pdf() output is parseable text (not image)
```

### 5.4 Playwright Rendering Architecture

```
build_pdf(cv_data, template_id) [async]
    |
    +-- render_html(cv_data, template_id)
    |     +-- _resolve_template(template_id) -> Path (fallback to cv_template.html if unknown)
    |     +-- template.read_text() -> HTML string
    |     +-- _inject(template, _flatten(cv_data)) -> rendered HTML
    |
    +-- async_playwright()
          +-- chromium.launch()
          +-- page.set_content(html_str, wait_until="networkidle")
          +-- page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
          +-- browser.close()
          -> raw PDF bytes
```

**Performance note:** `chromium.launch()` adds ~200ms per call. The Live Editor triggers `render-pdf` on every Save. For MVP this latency is acceptable. Post-MVP optimization: keep a warm browser instance in the FastAPI lifespan.

---

## 6. Feature 4 — Live Editor

### 6.1 Implementation Status

**Fully implemented — stateless backend, stateful frontend.**

| Component | File | Status |
|---|---|---|
| `LiveEditor` component | `web_dashboard/src/components/LiveEditor.tsx` | Done |
| `EditableField` auto-resize textarea | `web_dashboard/src/components/LiveEditor.tsx` | Done |
| `SkillCategoryEditor` tag chips | `web_dashboard/src/components/LiveEditor.tsx` | Done |
| `CvData` TypeScript interface | `web_dashboard/src/components/LiveEditor.tsx` | Done |
| `ApplierPreview` state wiring | `web_dashboard/src/components/ApplierPreview.tsx` | Done |
| `handleEditorSave` (parallel match-score + render-pdf) | `web_dashboard/src/components/ApplierPreview.tsx:430-447` | Done |
| `handleSelectTemplate` | `web_dashboard/src/components/ApplierPreview.tsx:449-457` | Done |
| `handleEditorReset` | `web_dashboard/src/components/ApplierPreview.tsx:424-428` | Done |

### 6.2 State Machine — ApplierPreview

```
State variables:
  phase:            'idle' | 'generating' | 'missing_data' | 'preview' | 'revising' | 'applying'
  cvState:          { cvData, pdfB64 } | null
  editedCvData:     CvData | null     — mutable working copy
  originalCvData:   CvData | null     — immutable snapshot from last generation
  isDirty:          boolean
  isSaving:         boolean
  matchScore:       MatchScoreResult | null
  selectedTemplate: string            — defaults to "t2_modern"
  templates:        TemplateInfo[]    — loaded on mount from GET /templates
  isEditMode:       boolean

Transitions:
  'idle'         -> 'generating'   : handleGenerate()
  'generating'   -> 'missing_data' : TailorAgent returns missing_data
  'generating'   -> 'preview'      : TailorAgent returns cv_data + score
  'missing_data' -> 'generating'   : handleSubmitInfo() or handleSkipInfo()
  'preview'      -> 'revising'     : handleRevise()
  'revising'     -> 'preview'      : gatekeeper approves or rejects
  'preview'      -> 'applying'     : handleApprove()
  any            -> 'idle'         : handleRegenerate() (resets all B2C state)
```

### 6.3 CvData Interface Contract

The `CvData` TypeScript interface in `LiveEditor.tsx` mirrors the `cv_data` dict from `TailorAgent`:

```typescript
export interface CvData {
  title:        string
  summary:      string
  experience:   Array<{
    role:    string; company: string; dates: string; bullets: string[]
  }>
  education:    Array<{
    degree: string; institution: string; dates: string; honors: string; coursework: string
  }>
  military?:    { role: string; unit: string; dates: string }
  skills:       { categories: Array<{ label: string; items: string[] }> }
  languages:    Array<{ language: string; level: string }>
  volunteering: string
  [key: string]: unknown   // preserves extra fields for pass-through to /render-pdf
}
```

### 6.4 Auto-Save Design

```typescript
const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

useEffect(() => {
  if (!isDirty) return
  if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
  saveTimerRef.current = setTimeout(onSave, 30_000)
  return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current) }
}, [cvData, isDirty, onSave])
```

The timer resets on every `cvData` change — the 30-second clock only fires after 30 continuous seconds of inactivity. If `isSaving` is already `true` when the timer fires, `handleEditorSave` returns early, preventing a double-save.

---

## 7. API Contract — Full Endpoint Inventory

All endpoints are implemented. This documents the complete contract for reference and testing.

### 7.1 Existing B2C Endpoints (all in `resumes.py`)

#### `POST /api/resumes/tailor`
```
Request:  { job_id: string, supplemental_answers?: Record<string, string> }
Response (ok):           { status:"ok", cv_data, pdf_b64, match_score, preferred_template }
Response (missing_data): { status:"missing_data", missing_data_requests:[{id,question,context}] }
LLM: Claude Sonnet (cv generation) + Claude Haiku (match score Phase 2)
Latency: ~15-30s first call; ~2s on re-run with answers
```

#### `POST /api/resumes/render-pdf`
```
Request:  { cv_data: CvData, template_id?: string }
Response: { pdf_b64: string }
LLM: None
Latency: ~300-600ms (Playwright launch + render)
```

#### `POST /api/resumes/match-score`
```
Request:  { job_id: string, cv_data: CvData, llm_validation?: boolean }
Response: MatchScoreResult (total, keyword_overlap, skills_alignment, seniority_alignment,
          matched_keywords, missing_keywords, matched_skills, missing_skills, suggestions, llm_validated)
LLM: Claude Haiku only when llm_validation=true
Latency: <100ms (Phase 1) | ~2s (Phase 2)
```

#### `GET /api/resumes/templates`
```
Response: { templates: [{ id, name, description }] }
Static, no I/O
```

#### `POST /api/resumes/revise`
```
Request:  { job_id: string, revision_text: string, cv_data: CvData }
Response: { status:"approved"|"rejected", message, cv_data?, pdf_b64? }
LLM: Claude Sonnet (RevisionGatekeeper)
```

### 7.2 New Endpoints Required (Master Profile)

#### `GET /api/profile`
```
Response: master_profile.json as JSON
Auth: none
```

#### `PUT /api/profile/personal`
```
Request:  { field: "phone"|"location"|"linkedin_url", value: string }
Response: { updated: true }
Side-effect: syncs phone/location into USER_PROFILE["personal"] in memory
```

#### `PUT /api/profile/metrics`
```
Request:  { question_id: string, value: string | null }
Response: { updated: true } | { deleted: true }
value=null -> deletes the entry
```

---

## 8. Module Change Map

### 8.1 Files to Create

| File | Purpose | Priority |
|---|---|---|
| `backend/services/master_profile_service.py` | Structured profile store: `load`, `save`, `get_cached_answer`, `merge_answers`, `bootstrap_from_supplemental` | P0 |
| `backend/api/routes/profile.py` | REST endpoints for profile view/edit (`GET /api/profile`, `PUT /api/profile/personal`, `PUT /api/profile/metrics`) | P1 |

### 8.2 Files to Modify

| File | Change | Lines affected | Priority |
|---|---|---|---|
| `backend/api/routes/resumes.py` | Add `merge_answers()` call in `/tailor` success path; add auto-fill logic for cached answers in missing_data path | ~240-260 | P0 |
| `backend/main.py` | Add `bootstrap_from_supplemental()` call in lifespan; register `profile.router` | lifespan block; router includes | P0 / P1 |

### 8.3 Files Complete — Do Not Modify

| File | Reason |
|---|---|
| `backend/services/match_score_service.py` | Feature complete |
| `backend/services/pdf_builder.py` | Feature complete |
| `backend/services/supplemental_store.py` | Flat store retained; master_profile_service wraps it, does not replace it |
| `backend/agents/tailor.py` | Feature complete — XYZ framework, METRICS EXTRACTION, PASSIVE VOICE BAN all present |
| `backend/templates/cv/t1_classic.html` | Feature complete |
| `backend/templates/cv/t2_modern.html` | Feature complete |
| `backend/templates/cv/t3_executive.html` | Feature complete |
| `web_dashboard/src/components/MatchScorePanel.tsx` | Feature complete |
| `web_dashboard/src/components/TemplateSelectorBar.tsx` | Feature complete |
| `web_dashboard/src/components/LiveEditor.tsx` | Feature complete |
| `web_dashboard/src/components/ApplierPreview.tsx` | Feature complete |
| `web_dashboard/src/lib/api.ts` | Feature complete |
| `web_dashboard/src/lib/apiTypes.ts` | Feature complete |

### 8.4 Files to Audit Before Touching

| File | Risk |
|---|---|
| `backend/services/profile_manager.py` | Unknown content — read before modification; may overlap with master_profile_service |
| `backend/engines/master_profile.py` | Bullet improvement system — completely different concern; do NOT extend for B2C |

---

## 9. Non-Breaking Guarantees

The following invariants must hold after all B2C changes. No existing functionality may regress.

| Invariant | How Guaranteed |
|---|---|
| `POST /tailor` without `supplemental_answers` still works | `supplemental_answers` is optional; auto-fill logic short-circuits cleanly when no requests present |
| `build_pdf(cv_data)` with no `template_id` uses legacy template | `_resolve_template(None)` falls back to `TEMPLATE_PATH = .../cv_template.html` |
| `supplemental_answers.json` flat store is not replaced | `master_profile_service.py` writes to a **different file** (`data/master_profile.json`); flat store continues unmodified |
| `USER_PROFILE["personal"]` remains the contact source for all PDF renders | `pdf_builder._load_contact()` reads from `USER_PROFILE` directly; not modified |
| `personal_overrides.json` phone/location persistence unchanged | `save_personal_field()` in `user_profile.py` is not modified; master_profile_service only calls it |
| `ResumeAgent` + `POST /generate` unchanged | These are the older multi-step flow; B2C features only touch the `/tailor` path |
| `RevisionGatekeeper` + `POST /revise` unchanged | Revision flow is independent of the Live Editor state |
| `engines/master_profile.py` (bullet improvements) unchanged | No imports, no modifications; naming coexists |

---

## 10. Implementation Order

Ordered by dependency and risk. Each step is independently testable.

### Phase A — Backend Core (P0, ~2 days)

**Step 1:** Create `backend/services/master_profile_service.py`
- Implement `load()`, `save()` (atomic), `get_cached_answer()`, `merge_answers()`, `bootstrap_from_supplemental()`
- Unit test: create profile, merge 3 answers, reload and verify fields
- Unit test: `bootstrap_from_supplemental()` reads fixture `supplemental_answers.json`

**Step 2:** Modify `backend/main.py`
- Add `bootstrap_from_supplemental()` in lifespan (wrapped in try/except)
- Smoke test: app starts, profile file created at `data/master_profile.json` if absent

**Step 3:** Modify `backend/api/routes/resumes.py`
- In `/tailor` success path: call `merge_answers(jd_answers)`
- In `/tailor` missing_data path: call `get_cached_answer()` per request; re-run with auto-filled answers on any hit
- Integration test: tailor once with answer; tailor again for same job — verify question is NOT re-asked

### Phase B — Profile API (P1, ~1 day)

**Step 4:** Create `backend/api/routes/profile.py`
- `GET /api/profile`, `PUT /api/profile/personal`, `PUT /api/profile/metrics`
- Register in `main.py`
- Test: GET returns schema; PUT personal syncs USER_PROFILE in memory

### Phase C — Verification (before launch)

**Step 5:** ATS template audit
- Run all 3 templates through PDFMiner; verify text extraction produces clean, ordered text

**Step 6:** Match score calibration
- Run Phase 1 on 5 real job pairs; verify score distribution is sensible (not all 0 or 100)

**Step 7:** Live Editor end-to-end regression
- Browser test: generate -> edit -> save -> re-score -> template switch -> back to preview

**Step 8:** Profile auto-fill regression
- Tailor 3 different jobs in sequence; verify previously answered questions never re-appear in the missing_data form
