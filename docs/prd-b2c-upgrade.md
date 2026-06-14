# PRD: B2C Upgrade — Sprint Release
**Product:** JobApply Venture — AI-Driven Career Matching & Resume Generation Platform
**Author:** Senior Product Manager
**Date:** 2026-05-08
**Status:** Draft v1.0

---

## 1. Executive Summary

This PRD defines the requirements for four features comprising the B2C Upgrade sprint. These features close the gap between our current internal tooling and the consumer-grade experience offered by market leaders (Rezi, Kickresume, Wonsulting). The features — Master Profile, Match Score, Template Engine, and Live Editor — form a cohesive end-to-end workflow: a user maintains a persistent profile, applies to a job with a quantified match score, selects a visual template, edits the result live, and exports a PDF. Together they are designed to increase resume generation quality, reduce time-to-export, and improve user retention.

---

## 2. Background & Strategic Context

### 2.1 Market Research Findings

| Competitor | Strengths Observed |
|---|---|
| Rezi | ATS keyword scoring, persistent answer library, real-time ATS score on editor |
| Kickresume | Strong template variety, inline editing, instant PDF preview |
| Wonsulting | AI-powered resume bullet generation, coaching-oriented UX, profile persistence |

### 2.2 Current State Gaps

- **No profile persistence:** Users re-enter supplemental context on every run, creating friction and inconsistency.
- **No match visibility:** Users receive a generated CV but have no quantified signal of fit for the specific job.
- **Single implicit template:** Output styling is hardcoded; no user choice or ATS-safety guarantee.
- **No post-generation editing:** Any correction requires a full re-run, increasing latency and LLM cost.

### 2.3 Business Goals

- Increase resume generation completion rate (target: +20% vs. baseline).
- Reduce average time from job URL input to PDF export (target: ≤ 4 minutes).
- Enable freemium monetization hooks via template and profile features.
- Lay data foundation for future personalized job recommendation engine.

---

## 3. Target Users

**Primary:** Job seekers (individual contributors through senior managers) actively applying to roles, comfortable with AI-assisted tools.

**Secondary:** Career changers who need heavy tailoring and value match score transparency to prioritize applications.

**Out of scope:** Recruiters, enterprise HR systems, bulk application flows.

---

## 4. Feature Scope & Priority

| Feature | Priority | MVP? |
|---|---|---|
| Master Profile | P0 | Yes |
| Match Score | P0 | Yes |
| Template Engine | P1 | Yes (3 templates) |
| Live Editor | P1 | Yes |

All four features ship together as MVP; they are interdependent in the user flow.

---

## 5. Feature Requirements

---

### 5.1 Feature 1: Master Profile

#### 5.1.1 Problem Statement
Every CV generation session today requires the user to re-supply supplemental context (achievements, preferences, constraints). This creates friction, inconsistency across applications, and prevents learning over time.

#### 5.1.2 User Story
> As a job seeker, I want my answers to supplemental questions saved so that future CV generations are pre-filled and I only have to update what has changed.

#### 5.1.3 Functional Requirements

**P0 — Core**
- The system SHALL persist a `master_profile` data structure per user, stored server-side (keyed to user session or account ID).
- On any CV generation run, the system SHALL pre-populate all supplemental input fields from the master profile.
- After a successful CV generation, any new or modified supplemental answers SHALL be merged back into the master profile (upsert, not replace).
- The user SHALL be able to view and edit their master profile from a dedicated Profile page at any time between runs.

**P1 — Enhanced**
- Profile fields SHALL include: name, contact info, target roles, target industries, years of experience, top 5 skills, career narrative summary, compensation expectations, work authorization, notable achievements (freeform list), preferred work mode (remote/hybrid/onsite).
- The system SHALL timestamp each field's last-updated date, displayed to the user on the profile page.
- Supplemental Q&A pairs from completed runs SHALL be appended to a `qa_history` log within the profile, deduplicated by question hash.

**P2 — Future**
- Cross-device sync via authenticated account.
- Profile completeness indicator (0–100%) with prompts to fill gaps.

#### 5.1.4 Data Model (Proposed)

```json
{
  "user_id": "string",
  "name": "string",
  "contact": { "email": "string", "phone": "string", "linkedin": "string" },
  "target_roles": ["string"],
  "target_industries": ["string"],
  "skills": ["string"],
  "career_summary": "string",
  "achievements": ["string"],
  "work_authorization": "string",
  "preferred_mode": "remote | hybrid | onsite",
  "compensation_range": { "min": "number", "max": "number", "currency": "string" },
  "qa_history": [
    { "question_hash": "string", "question": "string", "answer": "string", "last_used": "ISO8601" }
  ],
  "updated_at": "ISO8601"
}
```

Storage: JSON file per user in `data/profiles/` directory (matching existing `data/` pattern); migrate to DB when user count warrants.

#### 5.1.5 UX Flows

**Flow A — First run (no profile):**
1. User submits JD URL → supplemental questions appear as empty fields.
2. User completes fields → CV generated.
3. System saves answers as new master profile, shows toast: "Profile saved for next time."

**Flow B — Returning user:**
1. User submits JD URL → supplemental fields pre-populated from profile.
2. User reviews, edits if needed → CV generated.
3. Changed answers merged back; unchanged answers retained.

**Flow C — Direct profile edit:**
1. User navigates to `/profile` → sees all fields in editable form.
2. User edits → saves → profile updated immediately (no CV run required).

#### 5.1.6 Acceptance Criteria
- [ ] Supplemental fields are pre-populated on second and subsequent runs.
- [ ] Edits made during a run persist to the profile after generation.
- [ ] Profile page loads and saves independently of any CV run.
- [ ] Empty profile state (first run) does not break the generation flow.
- [ ] Profile data survives a browser refresh (server-side persistence confirmed).

---

### 5.2 Feature 2: Match Score

#### 5.2.1 Problem Statement
Users have no quantified signal of how well their CV targets a specific job description. Without this, they cannot prioritize applications or know when to stop iterating.

#### 5.2.2 User Story
> As a job seeker, I want to see a percentage match score between my CV and the job description so I can understand how competitive my application is and decide whether to keep refining it.

#### 5.2.3 Functional Requirements

**P0 — Core**
- After CV generation, the system SHALL compute and display a 0–100% Match Score.
- The score SHALL be displayed prominently on the results page before the PDF export button.
- The score SHALL be computed from: (a) keyword overlap between JD and CV text, (b) skills alignment, (c) seniority/title alignment.
- The system SHALL display a breakdown of the score in at least three sub-dimensions (see algorithm below).

**P1 — Enhanced**
- Each sub-dimension SHALL show which JD keywords were matched vs. missing.
- Missing high-importance keywords SHALL be surfaced as actionable suggestions: "Consider adding: [keyword]."
- Score SHALL re-compute automatically when the Live Editor saves changes (see Feature 4).

**P2 — Future**
- Benchmark score against anonymized distribution for the same role category.
- Track score history across multiple iterations of the same application.

#### 5.2.4 Scoring Algorithm

```
Match Score (0–100) = weighted sum of three components:

1. Keyword Overlap (40%)
   - Extract noun phrases and technical terms from JD (NLP tokenization)
   - Count matched terms present in CV text
   - Score = (matched / total_jd_keywords) * 40

2. Skills Alignment (35%)
   - Compare JD required/preferred skills list vs. CV skills section
   - Exact match = 1.0, semantic near-match = 0.6, missing = 0.0
   - Score = (weighted_matched_skills / total_jd_skills) * 35

3. Seniority & Title Alignment (25%)
   - Extract target seniority from JD title (Junior/Mid/Senior/Lead/Principal/Director)
   - Extract user's most recent title from CV
   - Exact = 1.0, one-level delta = 0.7, two-level delta = 0.4, mismatch = 0.1
   - Score = alignment_factor * 25

Final Score = round(component_1 + component_2 + component_3)
```

Implementation note: leverage existing `orchestrator.py` and `models/` infrastructure; keyword extraction can use the existing LLM pipeline or a lightweight spaCy pass depending on latency budget.

#### 5.2.5 UI Display

- Large circular gauge or progress bar showing the total score (e.g., "78%").
- Color coding: 0–49% red, 50–74% amber, 75–100% green.
- Expandable breakdown panel showing three sub-dimension bars.
- "Missing Keywords" chip list with copy-to-clipboard per keyword.

#### 5.2.6 Acceptance Criteria
- [ ] Score displayed on results page after every generation.
- [ ] Score is between 0 and 100 inclusive.
- [ ] Three sub-dimension scores sum to the total score (within rounding).
- [ ] Missing keyword suggestions are present and accurate.
- [ ] Score updates within 3 seconds of a Live Editor save.
- [ ] Score computation does not block PDF export (async or pre-computed).

---

### 5.3 Feature 3: Template Engine

#### 5.3.1 Problem Statement
The platform outputs a single implicitly styled CV. Users have no choice in visual format, and there is no guarantee of ATS safety across different parsing systems.

#### 5.3.2 User Story
> As a job seeker, I want to choose from multiple resume templates that are guaranteed to pass ATS parsers, so I can match my application's visual style to the company culture without sacrificing machine readability.

#### 5.3.3 Functional Requirements

**P0 — Core**
- The system SHALL offer exactly 3 ATS-safe HTML/CSS templates at launch.
- Template selection SHALL occur before PDF export, on the results page.
- Switching templates SHALL re-render the CV content into the new template without re-running the LLM.
- All templates SHALL pass ATS safety rules (see constraints below).

**P1 — Enhanced**
- Template thumbnails (static preview images) SHALL be shown in a selection row.
- Selected template SHALL be highlighted with a border/check indicator.
- Last-used template SHALL be remembered per user in the master profile.

**P2 — Future**
- Premium template tier (4th+ templates) as a monetization hook.
- Company-specific template recommendations based on industry.

#### 5.3.4 Template Specifications

All three templates must comply with ATS Safety Rules:
- Single-column layout only (no multi-column tables for main content).
- No text boxes, headers/footers as primary content containers, or text-in-images.
- Standard section headings: "Experience", "Education", "Skills", "Summary".
- Fonts: system-safe only (Arial, Calibri, Georgia, Times New Roman).
- No background colors on text, no icons replacing text labels.
- Machine-readable date formats (e.g., "Jan 2023 – Present").

| Template | Name | Visual Character | Font | Accent |
|---|---|---|---|---|
| T1 | **Classic** | Traditional, conservative | Times New Roman | Black only |
| T2 | **Modern** | Clean, minimal, subtle rule lines | Arial | Single accent color (dark blue) |
| T3 | **Executive** | Bold section headers, generous whitespace | Georgia | Dark charcoal headers |

Implementation: Each template is a standalone Jinja2 HTML template in `templates/cv/`. The CV data model (structured dict from LLM output) is injected at render time. PDF export uses the existing `weasyprint` or `pdfkit` pipeline (confirm with backend).

#### 5.3.5 Acceptance Criteria
- [ ] All three templates render without content loss when switching.
- [ ] Template switch takes < 1 second (client-side re-render preferred).
- [ ] All templates produce PDFs that parse correctly in a reference ATS simulator (e.g., Jobscan or equivalent manual check).
- [ ] Selected template persists if the user navigates away and returns.
- [ ] No LLM call is triggered by template switching alone.

---

### 5.4 Feature 4: Live Editor

#### 5.4.1 Problem Statement
Post-generation corrections require a full re-run today, incurring latency (30–90s) and LLM cost. Users need micro-corrections (typo, wording, adding a line) that do not justify a full pipeline re-run.

#### 5.4.2 User Story
> As a job seeker, I want to make small edits to my generated CV directly in the browser before exporting it, so I can fix wording or add details without waiting for a full regeneration.

#### 5.4.3 Functional Requirements

**P0 — Core**
- The results page SHALL render the CV content in an editable state (contenteditable or structured form fields per section).
- Users SHALL be able to edit any text field: summary, bullet points, skills, dates, titles, contact info.
- An explicit "Save" action SHALL commit changes to the in-memory CV state.
- PDF export SHALL always use the most recently saved in-editor state.

**P1 — Enhanced**
- "Undo" (Ctrl+Z / Cmd+Z) SHALL revert the last edit within the session.
- Changes SHALL be auto-saved to session state every 30 seconds to prevent data loss.
- Edited fields SHALL show a subtle visual indicator (e.g., light yellow highlight) until saved.
- After save, Match Score SHALL recompute against the edited text (see Feature 2, P1).
- A "Reset to Generated" button SHALL restore the original LLM output, with a confirmation dialog.

**P2 — Future**
- AI-assisted rewrite suggestions on selected text (right-click context menu).
- Track changes view comparing original vs. edited version.

#### 5.4.4 Editor Architecture

- The CV structured data object (dict) is the source of truth, not raw HTML.
- Editor renders the structured data into the selected template's HTML for display.
- Edits are captured at the field level (not as raw HTML mutations) to maintain data integrity.
- On "Save": field-level changes written back to the structured data object; template re-renders from updated data.
- On "Export PDF": the current structured data object + selected template are passed to the PDF pipeline.

This approach ensures template switching after editing does not lose edited content.

#### 5.4.5 Acceptance Criteria
- [ ] All visible text fields are editable inline.
- [ ] Save commits changes; subsequent PDF export reflects edits.
- [ ] Undo reverts the last change within the session.
- [ ] "Reset to Generated" restores original LLM output after confirmation.
- [ ] Auto-save fires every 30 seconds and does not interrupt user typing.
- [ ] Editing does not trigger a new LLM call.
- [ ] Match Score updates after Save (within 3 seconds).

---

## 6. End-to-End User Flow (All Four Features Combined)

```
[User lands on app]
        |
        v
[Enters JD URL]
        |
        v
[Supplemental fields pre-populated from Master Profile]  <-- Feature 1
        |
[User reviews / updates fields]
        |
        v
[CV Generation runs (existing LLM pipeline)]
        |
        v
[Results Page]
  |           |           |
  v           v           v
[Match Score]  [Template   [Live Editor]
 displayed     selector]   (editable CV)
 (Feature 2)  (Feature 3)  (Feature 4)
                  |              |
                  +------+-------+
                         |
                         v
              [Template re-renders with edited content]
                         |
                         v
              [Match Score recomputes on Save]
                         |
                         v
              [Export to PDF]
                         |
                         v
              [Master Profile updated with session answers]  <-- Feature 1 write-back
```

---

## 7. Non-Functional Requirements

| Requirement | Target |
|---|---|
| CV generation end-to-end latency | ≤ 60s (existing), no regression |
| Template switch render time | < 1s |
| Match Score compute time | < 5s post-generation, < 3s post-edit |
| Live Editor save response time | < 500ms |
| Profile load time | < 300ms |
| PDF export time | < 10s |
| ATS compatibility | 100% of templates pass standard ATS parsing |
| Mobile responsiveness | Results page editor usable on tablet (≥768px) |

---

## 8. Out of Scope (This Sprint)

- User authentication / account system (profile stored per session for MVP).
- More than 3 templates.
- AI rewrite suggestions in Live Editor.
- Batch job application flows.
- Recruiter-facing features.
- Score benchmarking against other users.
- Integrations with external job boards (LinkedIn Easy Apply, etc.).

---

## 9. Dependencies & Risks

| Item | Type | Mitigation |
|---|---|---|
| PDF rendering library compatibility with new templates | Technical | Validate T1/T2/T3 with weasyprint/pdfkit early in dev; include a render smoke test |
| LLM output structured data format may vary | Technical | Add output schema validation in orchestrator.py before passing to editor/template |
| Match Score NLP accuracy | Product | Ship with keyword overlap only for MVP; skills/seniority scoring can be progressive enhancement |
| Session-only profile persistence (no auth) | Product risk | Clearly communicate to user; implement browser localStorage fallback as interim measure |
| contenteditable cross-browser inconsistency | Technical | Evaluate structured form-fields approach as safer alternative; decide in tech spike |

---

## 10. Success Metrics

| Metric | Baseline | Target (30 days post-launch) |
|---|---|---|
| Resume generation completion rate | TBD (measure at launch) | +20% |
| Time from JD input to PDF export | TBD | ≤ 4 minutes |
| % users who edit in Live Editor | 0% | ≥ 40% |
| % users who switch templates | 0% | ≥ 30% |
| Average Match Score at export | TBD | ≥ 70% |
| Profile pre-population rate (run 2+) | 0% | ≥ 80% |

---

## 11. Open Questions

1. **Auth**: Is session-based profile storage acceptable for MVP, or do we need a lightweight auth layer (e.g., magic link email)?
2. **Score algorithm**: Do we use the existing LLM for keyword extraction (higher accuracy, slower) or a local NLP library like spaCy (faster, less accurate)?
3. **PDF library**: Confirm whether current stack uses weasyprint or pdfkit; this affects template CSS constraints.
4. **Editor approach**: contenteditable div vs. structured field-by-field form — needs a 1-day tech spike to validate.
5. **Template design assets**: Who produces the template thumbnails for the selection UI — PM, designer, or AI-generated?

---

## 12. Appendix: File & Directory Conventions

Following the existing project structure:

```
/
├── CLAUDE.md
├── app.py                    # Flask/web entry point
├── orchestrator.py           # CV generation pipeline
├── models/                   # LLM model configs
├── data/
│   └── profiles/             # NEW: master profile JSON files (per user/session)
├── templates/
│   └── cv/                   # NEW: T1_classic.html, T2_modern.html, T3_executive.html
├── web_dashboard/
│   └── ...                   # Frontend assets; Live Editor UI lives here
└── docs/
    └── prd-b2c-upgrade.md    # This document
```
