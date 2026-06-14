# Product Requirements Document: B2C Upgrade
**Project:** JobApply_Venture  
**Version:** 1.0  
**Date:** 2026-05-08  
**Author:** Senior Product Manager  
**Status:** Approved for Development

---

## Table of Contents
1. [Step 1 — Context & Business Goals](#step-1--context--business-goals)
2. [Step 2 — User Research & Personas](#step-2--user-research--personas)
3. [Step 3 — Feature Design](#step-3--feature-design)
4. [Step 4 — Humanistic Design](#step-4--humanistic-design)
5. [Appendix — Success Metrics & Open Questions](#appendix)

---

## Step 1 — Context & Business Goals

### 1.1 Product Vision
JobApply_Venture is an AI-driven career matching platform that generates ATS-optimized, single-page CVs tailored to individual job descriptions. The B2C Upgrade shifts the platform from a raw backend tool into a consumer-grade product with transparency, personalization, and user control as first-class values.

### 1.2 Business Goals
| Goal | Rationale |
|---|---|
| Increase perceived output quality | Users distrust black-box AI; showing a match score and letting them edit creates ownership and trust |
| Reduce "one and done" abandonment | A saved Master Profile lowers re-entry friction so users return for every application |
| Differentiate from Rezi / Kickresume | Match Score + Live Editor together are not offered as a tightly integrated loop by any current competitor |
| Capture qualitative signals | Supplemental answers saved to the Master Profile become a proprietary training corpus for future fine-tuning |

### 1.3 Scope & Constraints
- **Authentication:** None in this sprint. All persistence is local flat-file (JSON) keyed to a single user. Multi-user support is explicitly out of scope.
- **PDF Renderer:** Playwright/Chromium pipeline is fixed. All HTML/CSS templates must be Chromium-compatible. No WeasyPrint, no pdfkit.
- **LLM Budget:** Match Score LLM validation uses Claude Haiku (cheapest tier) and is capped at one call per CV generation. Live Editor re-scores use Phase 1 Python only (no LLM call on every keystroke).
- **No mobile:** The editor and preview panel require ≥1024px viewport. Mobile is deferred.
- **Timeline:** All four features ship as one sprint. No feature flags or phased rollout.

### 1.4 Competitive Landscape
| Competitor | Match Score | Template Engine | Live Editor | Master Profile |
|---|---|---|---|---|
| Rezi | ✅ keyword only | 10+ templates | ✅ rich | ❌ |
| Kickresume | ❌ | 35+ templates | ✅ rich | ❌ |
| Wonsulting | ❌ | 3 templates | ❌ | ❌ |
| **JobApply_Venture (post-upgrade)** | **✅ algorithmic + AI** | **✅ 3 ATS-safe** | **✅ structured** | **✅ persistent** |

Our differentiation is the closed loop: generate → score → edit → re-score → export, without ever leaving the screen.

---

## Step 2 — User Research & Personas

### 2.1 Persona A — "The Anxious Career Switcher" (Primary)
**Name:** Maya, 29  
**Background:** 5 years in B2B SaaS customer success. Wants to transition into product management. Applies to 3–5 roles per week, spends 2+ hours tailoring each CV manually.

**Goals:**
- Know immediately whether her CV is strong enough for a specific role before applying
- Not repeat herself — she's answered "What metrics did you own?" fifteen times across different tools
- Feel confident, not overwhelmed, by the AI output

**Pain Points:**
- "I never know if the AI actually read the job description or just wrote a generic CV"
- Afraid the AI fabricates numbers ("it said I managed a $2M budget, I never did")
- Template switching is tedious — she wants to see the difference visually before committing
- When she edits one bullet, the whole document re-generates and she loses her other tweaks

**Behaviors:**
- Opens the platform from a job board link immediately after seeing an interesting role
- Reads every bullet before approving
- Will spend up to 8 minutes editing if she feels the tool gives her control
- Abandons if first-generation output is weak and there's no quick fix path

**Emotional State at Key Moments:**
- *After generation:* Anxious — "Is this good enough?"
- *Seeing match score:* Relieved if ≥75%, frustrated if <50% with no explanation
- *In the editor:* In flow state if the UI is fast; frustrated by any lag >500ms

---

### 2.2 Persona B — "The High-Volume Applicant" (Secondary)
**Name:** David, 34  
**Background:** Software engineer, recently laid off. Applying to 15–20 roles per week across multiple geographies. Prioritizes speed over perfection.

**Goals:**
- Process each application in under 3 minutes
- Skip data-entry questions he's already answered before
- Download a clean PDF fast

**Pain Points:**
- Hates being asked the same supplemental question twice
- Doesn't care deeply about template aesthetics — just needs ATS-safe output
- Gets impatient with UI animations or multi-step confirmation dialogs

**Behaviors:**
- Uses "Skip all" on supplemental questions more than 60% of the time
- Will use the Live Editor only to fix an obvious factual error, not for stylistic tweaks
- Evaluates the match score as a binary "good enough / not" signal

---

### 2.3 Persona C — "The Senior Executive" (Edge / Aspirational)
**Name:** Sandra, 47  
**Background:** VP of Operations, targeting C-suite roles. Applies rarely (2–3 per month) but with extreme care.

**Goals:**
- The Executive template specifically — authoritative, serif font, thick rule separators
- Deep control: wants to edit every bullet and review word choice
- Match score with LLM validation as a quality gate before she sends anything

**Pain Points:**
- Afraid AI will "make her sound junior"
- Does not want passive voice or any of the "assisted in" / "supported the team" constructions
- Needs to trust that the numbers in her CV are exactly what she provided

**Behaviors:**
- Uses every minute of the editor session — reads, edits, saves, reads again
- Will request LLM validation explicitly even if it adds latency

---

## Step 3 — Feature Design

### 3.1 Feature 1 — Master Profile

#### 3.1.1 Overview
A persistent JSON store (`data/master_profile.json`) that accumulates all supplemental answers the user provides across job applications. When the TailorAgent requests a supplemental answer for a new job, the system first checks the profile for an existing answer to the same question before prompting the user.

#### 3.1.2 Priority Breakdown
| ID | Feature | Priority | Rationale |
|---|---|---|---|
| MP-01 | Read profile on every tailor request | P0 | Core value prop — never ask twice |
| MP-02 | Write/merge new answers after each successful generation | P0 | Enables MP-01 on subsequent runs |
| MP-03 | Structured schema: personal, metrics, role_preferences sections | P0 | Without structure, fuzzy matching degrades |
| MP-04 | Profile view/edit UI in settings panel | P1 | Users need transparency and correction ability |
| MP-05 | Answer confidence scoring (high/low based on recency + specificity) | P2 | Deprioritize uncertain old data over fresh answers |
| MP-06 | Export profile as JSON download | P2 | Portability / GDPR right to access |

#### 3.1.3 Data Schema
```json
{
  "version": 1,
  "last_updated": "ISO-8601 timestamp",
  "personal": {
    "full_name":    "string",
    "email":        "string",
    "phone":        "string",
    "linkedin_url": "string",
    "location":     "string"
  },
  "metrics": {
    "free-form key (question_id or slug)": {
      "value":      "string  — the user's answer",
      "source":     "supplemental | manual",
      "confidence": "high | medium | low",
      "created_at": "ISO-8601",
      "updated_at": "ISO-8601"
    }
  },
  "role_preferences": {
    "target_titles":    ["string"],
    "preferred_locations": ["string"],
    "work_type":        "remote | hybrid | onsite | any",
    "salary_min_usd":   "number | null"
  }
}
```

#### 3.1.4 Core Flow
1. User triggers "Generate CV" for Job X.
2. TailorAgent identifies missing context → returns `missing_data_requests[]`.
3. System queries `master_profile.json` by `question_id`.
4. **Hit:** inject cached answer, skip user prompt for that question.
5. **Miss:** display `MissingDataForm` for that question only.
6. After successful generation, `POST /api/profile/merge` writes new answers back.
7. Next application to Job Y: steps 3–4 hit for all previously answered questions.

#### 3.1.5 Edge Cases
| Scenario | Handling |
|---|---|
| Profile file missing on first run | Create empty profile with schema version; never throw |
| Answer stored 6+ months ago for a time-sensitive metric (e.g., team size) | Mark `confidence: low`; surface a "verify this answer" prompt before re-using |
| User provides a contradictory answer in the same session | Latest session answer wins; update profile immediately |
| `master_profile.json` fails to write (disk full, permissions) | Log warning, continue generation; never block CV output |
| Question text changes slightly between jobs (fuzzy match challenge) | Use `question_id` slug matching, not semantic similarity, in MVP |

---

### 3.2 Feature 2 — Match Score

#### 3.2.1 Overview
A 0–100 composite ATS match score computed after every CV generation. Phase 1 is a fast Python text-analysis pass (<100ms). Phase 2 is an optional Claude Haiku validation pass that adjusts the score by ±5 points and surfaces missing keywords and improvement suggestions.

#### 3.2.2 Priority Breakdown
| ID | Feature | Priority | Rationale |
|---|---|---|---|
| MS-01 | Phase 1: keyword overlap score (0–40 pts) | P0 | Core algorithmic signal |
| MS-02 | Phase 1: skills alignment score (0–35 pts) | P0 | Critical for technical roles |
| MS-03 | Phase 1: seniority alignment score (0–25 pts) | P0 | Prevents "senior" CVs for junior roles and vice versa |
| MS-04 | Visual CircleGauge with colour bands | P0 | Score without visual = useless |
| MS-05 | Missing keywords chips | P0 | Actionable — user knows what to add |
| MS-06 | Phase 2: Haiku LLM validation on first generation | P1 | Accuracy gain worth the latency |
| MS-07 | Live re-score (Phase 1 only) on editor Save | P1 | Closes the edit → re-score loop |
| MS-08 | LLM re-validation on explicit user request | P2 | Power users (Persona C) want this |
| MS-09 | Score history chart across applications | P2 | Retention / progress signal |

#### 3.2.3 Scoring Model
```
Total Score (0–100) =
  keyword_overlap     (0–40)  — % of JD keywords present in CV text
  + skills_alignment  (0–35)  — exact/substring/loose match against extracted JD skills
  + seniority_match   (0–25)  — delta between CV seniority level and JD seniority level
```

**Colour Bands:**
- ≥75: Green — "Strong match"
- 50–74: Amber — "Partial match"
- <50: Red — "Weak match"

**JD Proxy Construction** (since raw JD text is not stored):
```python
parts = [f"{job.title} at {job.company}"]
if job.why_ron:           parts.append(job.why_ron)
if job.scoring_rationale: parts.append(job.scoring_rationale)
if job.detailed_analysis and job.detailed_analysis.critical_gaps:
    parts.append("Required: " + ", ".join(job.detailed_analysis.critical_gaps))
jd_proxy = " ".join(parts)
```

#### 3.2.4 UI Component Spec — `MatchScorePanel`
- **Header row:** 72×72px SVG CircleGauge (animated stroke-dashoffset on mount) + score label + "ATS match score" subtitle + optional "AI-validated" badge
- **Sub-bars:** Three `SubBar` components — keyword overlap (max 40), skills alignment (max 35), seniority match (max 25)
- **Missing keywords:** Up to 8 `KeywordChip` components in red-tinted pills
- **Suggestions:** Up to 4 bullet strings from the Phase 2 LLM response
- **Loading state:** `opacity: 0.55` during re-score; no skeleton shimmer (too complex for MVP)

#### 3.2.5 Edge Cases
| Scenario | Handling |
|---|---|
| Job has no `why_ron` or `scoring_rationale` (new scrape) | JD proxy = title only; score will be lower and unreliable; show "Limited job data" tooltip |
| Phase 2 Haiku call times out | Surface Phase 1 result silently; never block the user on score loading |
| Score returns 0 (API error) | Do not render MatchScorePanel; show no score rather than misleading 0% |
| User edits CV, saves, re-score returns lower score | Show the new score without hiding the delta; no "undo score" |
| CV has no skills section (edge profile) | skills_alignment = 0; still show panel with 0/35 on that bar |

---

### 3.3 Feature 3 — Template Engine

#### 3.3.1 Overview
Three ATS-safe single-column HTML/CSS CV templates, selectable via a thumbnail strip in the preview panel. All templates are strictly ATS-compatible: no multi-column layouts, no text-in-images, no custom fonts beyond system stacks, no CSS grid or flexbox multi-column.

#### 3.3.2 Priority Breakdown
| ID | Feature | Priority | Rationale |
|---|---|---|---|
| TE-01 | t1_classic: Times New Roman serif, centred header | P0 | Default fallback; highest ATS compatibility |
| TE-02 | t2_modern: Arial/Helvetica, navy header block | P0 | Default for new generations; clean and professional |
| TE-03 | t3_executive: Georgia serif, thick rule, shaded section headers | P0 | Persona C requirement |
| TE-04 | `TemplateSelectorBar` with SVG CSS thumbnails | P0 | Visual selection without loading images |
| TE-05 | Live template switch: clicking thumbnail re-renders PDF immediately | P0 | Core UX of the selector |
| TE-06 | `preferred_template` returned by `/tailor` and persisted | P1 | Pre-select the best template per job type |
| TE-07 | 4th template (two-tone, skills sidebar) | P2 | Post-MVP; requires ATS safety audit |

#### 3.3.3 Template Spec Summary
| Template | Font Stack | Header Style | Section Titles | Bullet Style | Skills |
|---|---|---|---|---|---|
| Classic | Times New Roman, Georgia, serif | Centred name + italic title | Uppercase, letter-spaced, `border-bottom: 1px solid #111` | `list-style: disc` | Inline text "Label: a · b · c" |
| Modern | Arial, Helvetica, sans-serif | Navy block (#1E3A5F), white text | Small uppercase + `#1D4ED8` accent, 0.75px rule | `list-style: disc` | Pill chips (#EFF6FF bg, #1D4ED8 border) |
| Executive | Georgia, Times New Roman, serif | Left-aligned, 3px charcoal bottom border | Shaded grey `#F0F0F0`, `border-left: 3px solid charcoal`, uppercase | `list-style: square` | Inline text with `·` separators, italic |

#### 3.3.4 ATS Safety Checklist (All Templates)
- [ ] Single-column vertical flow only
- [ ] No `<table>` for layout
- [ ] No `position: absolute` for content
- [ ] No `column-count` or CSS multi-column
- [ ] No web fonts (Google Fonts, etc.) — system fonts only
- [ ] No SVG/image containing readable text
- [ ] Contact information in plain `<p>` tags, not header images
- [ ] Section titles in `<h2>` or `<h3>` — not `<div>` styled as headings
- [ ] Standard page margins ≥0.5in

#### 3.3.5 Edge Cases
| Scenario | Handling |
|---|---|
| Unknown `template_id` passed to `/render-pdf` | Fallback to `t2_modern`; log warning |
| Template HTML missing from disk | Raise `500` with message "Template file not found"; never serve a blank PDF |
| CV data has empty sections (no military, no volunteering) | Templates handle `{% if %}` guards for optional sections; never render empty `<section>` tags |
| Template renders >1 page for long CVs | No auto-truncation in MVP; page overflow warning is a P2 feature |

---

### 3.4 Feature 4 — Live Editor

#### 3.4.1 Overview
An inline structured editor mounted in the right pane of the CV preview modal. It replaces the PDF `<iframe>` when the user clicks "✎ Edit CV". The editor operates on a JS in-memory copy of `cv_data` — no LLM is called on changes. Only the user's manual edits are applied. Saving triggers a Phase 1 re-score and a PDF re-render.

#### 3.4.2 Priority Breakdown
| ID | Feature | Priority | Rationale |
|---|---|---|---|
| LE-01 | Edit Professional Summary (full textarea) | P0 | Most impactful single field |
| LE-02 | Edit Experience bullets (per-bullet textarea, per-role) | P0 | Core editing need |
| LE-03 | Add/remove Skill tags per category | P0 | Skills are the #1 missing-keyword source |
| LE-04 | Dirty highlighting (amber border on changed fields) | P0 | User must see what they changed |
| LE-05 | Save → re-score (Phase 1) + re-render PDF | P0 | Closes the edit → feedback loop |
| LE-06 | Reset → restore original AI-generated values | P0 | Safety net against bad edits |
| LE-07 | Auto-save after 30s of inactivity | P1 | Prevent data loss on accidental close |
| LE-08 | Edit job role title and company name | P1 | Edge case: AI got the company name wrong |
| LE-09 | Edit Education section | P1 | Relevant for career switchers (Persona A) |
| LE-10 | Undo/redo within session (Ctrl+Z) | P2 | Complex state; defer |
| LE-11 | AI-assist: "Improve this bullet" CTA per bullet | P2 | Requires separate LLM call per bullet; post-MVP |

#### 3.4.3 Component Architecture
```
LiveEditor
├── Toolbar
│   ├── "Live Editor" label + "· unsaved changes" badge
│   ├── Reset button (UndoIcon)
│   └── Save button (SaveIcon, disabled when !isDirty || isSaving)
├── Section: Professional Summary
│   └── EditableField (auto-resize textarea, highlight if dirty)
├── Section: Experience
│   └── For each role:
│       ├── Role title (static display)
│       ├── Company · Dates (static display)
│       └── For each bullet: EditableField (highlight if dirty vs. original)
└── Section: Skills
    └── For each category: SkillCategoryEditor
        ├── Category label
        ├── Existing skill chips (× to remove)
        └── Add skill input (Enter or + button)
```

#### 3.4.4 State Management
```typescript
// All held in ApplierPreview component state
editedCvData:   CvData | null   // mutable working copy
originalCvData: CvData | null   // immutable snapshot from last generation
isDirty:        boolean         // any field differs from originalCvData
isSaving:       boolean         // save API call in flight

// On Save:
Promise.all([
  fetchMatchScore(job.id, editedCvData, llm_validation=false),  // Phase 1 only
  renderPdf(editedCvData, selectedTemplate),
])
// → update matchScore state + cvState.pdfB64
// → setIsDirty(false)
```

#### 3.4.5 Core Flow (Happy Path)
1. User generates CV → `phase = 'preview'`, `originalCvData` and `editedCvData` both set to `data.cv_data`
2. User clicks "✎ Edit CV" → `isEditMode = true`, right pane switches to `<LiveEditor>`
3. User edits Summary bullet → `isDirty = true`, amber border appears on that field
4. User clicks Save → `isSaving = true`, both API calls fire in parallel
5. API calls resolve → `MatchScorePanel` updates, right-pane PDF re-renders, `isDirty = false`
6. User clicks "← Back to Preview" → `isEditMode = false`, right pane shows updated PDF

#### 3.4.6 Edge Cases
| Scenario | Handling |
|---|---|
| User clicks Reset with no dirty changes | Button always clickable; resets to original (idempotent) |
| User deletes all text from a bullet | Allow empty string; PDF will render an empty bullet — user is responsible |
| Save call fails (API down) | Keep `isDirty = true`; show no error toast in MVP (auto-save is the safety net) |
| User closes modal with unsaved changes | No "are you sure?" dialog in MVP; changes are lost (document before going live) |
| `cv_data` has extra fields beyond `CvData` interface | `[key: string]: unknown` index signature absorbs them; they pass through to `/render-pdf` |
| Skills category has 0 items after all removed | Render empty category with just the input; do not hide the category |
| Auto-save fires while save already in flight | `saveTimerRef` guard: `if (saveTimerRef.current) clearTimeout(...)` prevents double-save |

---

## Step 4 — Humanistic Design

### 4.1 Accessibility
| Area | Requirement | Implementation |
|---|---|---|
| Colour contrast | All text on coloured backgrounds must meet WCAG AA (≥4.5:1) | Test amber/green/red score bands against their background values |
| Focus indicators | All interactive elements (buttons, textareas, skill input) must have visible `:focus` ring | `focus:ring-2 focus:ring-blue-200` already applied in Tailwind classes |
| Screen reader labels | SVG icons used as buttons must have `aria-label` or `title` | UndoIcon/SaveIcon buttons have `title` props; add `aria-label` for SR |
| Keyboard navigation | Full editor must be navigable without mouse | Tab order flows: Toolbar → Summary → Experience bullets → Skills |
| Textarea resize | Auto-resize textareas should not trap keyboard users | Confirm `resize: none` + `overflow: hidden` does not conflict with OS keyboard nav |
| CircleGauge | SVG score gauge must have accessible text alternative | `<text>` element inside SVG already provides value; add `aria-label="Match score: {total}%"` to `<svg>` |

### 4.2 Emotional Design
**Principle:** The platform mediates a high-stakes, emotionally loaded activity. Users are job-seeking, often under financial or social stress. Every moment of friction or anxiety is a moment closer to abandonment.

| Moment | Emotional Risk | Design Response |
|---|---|---|
| First generation — waiting (15–30s) | Anxiety: "Is it doing anything?" | Show pulsing spinner + "Tailoring your CV…" copy; never a bare loading screen |
| Match score < 50% | Discouragement: "I'm not good enough for this role" | Label is "Weak match", not "Poor match" or "Failed"; immediately follow with specific "Missing keywords" and "Suggestions" — make it actionable, not a verdict |
| AI-generated bullet contains an error | Anger / distrust: "The AI lied to me" | Live Editor is the direct response: "you have full control" messaging in the toolbar |
| Unsaved changes on close | Regret: "I lost my work" | Auto-save (30s debounce) as silent safety net; P1 task is to add confirmation modal before close |
| High match score (≥75) | Confidence boost | Use green colour band and "Strong match" label explicitly — let the user feel good |
| Saving with `isSaving = true` | Uncertainty: "Did it save?" | Save button changes to "Saving…" immediately; re-enables with "Save" after completion |

### 4.3 Privacy & Ethics

#### Data Minimisation
- `master_profile.json` stores only what the user explicitly provides via supplemental answers. It does not scrape, infer, or store job application decisions.
- The profile is local to the server filesystem — it is never sent to a third-party API.
- The LLM (Haiku) receives only the CV text and the JD proxy. No PII from the profile is sent to the LLM in the match-score call.

#### Transparency
- The "AI-validated" badge on MatchScorePanel explicitly marks when the Haiku call was made, so users know an LLM contributed to the score.
- The score is broken into three sub-dimensions (keyword, skills, seniority) so users understand what drives it, rather than receiving an opaque number.
- "Missing keywords" are drawn directly from the JD proxy — they are not AI hallucinations.

#### Accuracy & Non-fabrication
- The TailorAgent system prompt contains an explicit PASSIVE VOICE BAN and a list of forbidden constructions ("Was responsible for", "Contributed to", etc.).
- A METRICS EXTRACTION step requires every bullet that *can* carry a number *must* carry a number — but only numbers sourced from supplemental answers or the Master Profile. Fabricated numbers are explicitly prohibited.
- The Live Editor gives the user the final word on every sentence in their own CV.

#### User Control
- Reset button restores the AI-generated original at any time.
- P2: Master Profile view/edit UI lets users correct or delete stored answers.
- P2: Export profile as JSON gives users portability and honours GDPR right to access.

### 4.4 Inclusive Design
- All CV templates use system fonts available on Windows, macOS, and Linux — no subset loading failures.
- The Live Editor's auto-expanding textareas accommodate users who write longer, more detailed bullet points (not penalised with a fixed-height box).
- Colour is never the *only* indicator of state: dirty fields show both amber colour *and* a changed border width; score bands show both colour *and* a text label ("Strong match").
- The supplemental answer form supports multi-sentence answers — users who need to provide narrative context are not constrained to a single line.

---

## Appendix — Success Metrics & Open Questions

### A.1 Success Metrics (Sprint)
| Metric | Target | Measurement |
|---|---|---|
| Match score display rate | 100% of successful generations show a score | Log: generations with `match_score != null` / total generations |
| Template switch rate | ≥20% of preview sessions switch template ≥1 time | Log: `templateId` changes per session |
| Live Editor open rate | ≥30% of preview sessions open the editor | Log: `isEditMode = true` events |
| Editor save rate | ≥60% of sessions that open editor hit Save | Log: successful `handleEditorSave` calls |
| Re-score delta | Mean absolute score change after 1 edit session ≥3pts | Log: initial score vs. post-save score |
| Master Profile hit rate | After 3+ applications, ≥70% of supplemental questions answered from cache | Log: `profile_hit` vs. `user_prompted` events |

### A.2 Open Questions
| # | Question | Owner | Resolution Needed By |
|---|---|---|---|
| 1 | Should auto-save also trigger a re-render and re-score, or just persist `editedCvData`? | PM + Eng | Before LE-07 implementation |
| 2 | What happens to the editor state when the user submits an AI revision request? Should `originalCvData` update to the revised output? | PM | Before revision flow testing |
| 3 | Do we surface the Phase 1 score immediately and then update it when Phase 2 resolves, or wait for Phase 2 before showing anything? | PM + Design | Before MS-06 implementation |
| 4 | Should the Master Profile store the full `cv_data` JSON per job application, enabling a "history" view? | PM | P2 scoping session |
| 5 | GDPR: if the product goes multi-user, does storing supplemental answers require a privacy policy and explicit consent flow? | Legal / PM | Before any auth sprint |

### A.3 Out of Scope (This Sprint)
- User authentication and multi-user support
- Mobile / responsive layout
- CV version history
- Bulk export (multiple jobs → multiple CVs)
- LinkedIn import / profile sync
- 4th+ CV template
- Undo/redo within the Live Editor
- AI-assist "improve this bullet" per-bullet CTA
- Score history chart across applications
- Master Profile UI (view/edit/delete stored answers)

---

## Appendix B — UI/UX Standards (Dashboard & Overview Page)

> These rules are mandatory for all frontend work. Non-compliant implementations must be corrected before merging.

### B.1 Overview Page — Top KPI Row

The Overview page header displays **three** metrics only:

| KPI | Source | Definition |
|---|---|---|
| Jobs Scanned Today | `feedJobs` filtered by `isNew` | New roles discovered by agents in the current session |
| High Matches | `feedJobs` where `match_score > 85.0` | Count of high-confidence fits |
| Actions Taken | `feedJobs` where `why_ron` is set OR `has_tailored_cv` is true | Analyses run or CVs tailored |

No other KPIs (active applications, interviews, response rate) appear on the Overview page.

### B.2 Live Pipeline Status Section

The "Agent Status Center" and the former "Working on it" panel are merged into a single **"Live Pipeline Status"** section. Layout:

1. **Intro banner** — gradient card with headline "Job Apply is searching while you focus on what matters." and a one-line sub-description. Sits above the agent cards.
2. **Section header** — "Agent Status" label + "Run Pipeline" trigger button.
3. **Agent cards (×4)** — one card per agent, read-only.

**What agent cards must NOT contain:**
- Throughput sparkline charts
- Queue count numbers
- Any developer/backend metrics

**What agent cards must contain:**
- Agent name
- Status badge (label + color dot)
- Live status text — **never truncated**; wraps to 2–3 lines if needed

### B.3 Agent Status Color Semantics

| Visual | CSS Tone | Agent State(s) |
|---|---|---|
| **Gray dot** (static) | `muted` | `idle`, `paused` |
| **Pulsing blue dot** | `primary` with `pulse=true` | `active`, `queued` |
| **Solid green dot** (section level) | `success` | Pipeline completed (toast/banner) |
| **Pulsing red dot** | `danger` with `pulse=true` | `error` |

### B.4 Job Card — Accordion Pattern

All job cards across every tab (Overview, Matches feed) use the **Accordion pattern**:

- **Collapsed (default):** Score ring · Title · Company · Location · Source badge · Reason tags · Chevron. The entire row is the click target. No action buttons visible.
- **Expanded (on click):** AI Analysis (`why_ron`) → Action bar (Source link, Skip, Save, Outreach, Tailor CV) → Job description → ATS Keyword Gap Analysis.

This pattern eliminates "button soup" on long lists. Action buttons appear only after the user signals intent by expanding.

### B.5 ATS Score Formatting — One Decimal Place Rule

**All ATS match scores displayed anywhere in the UI must use exactly one decimal place.**

```
✅  87.8    94.0    63.5    100.0
❌  87      94      63.5234
```

Implementation: always call `score.toFixed(1)` before rendering. This applies to:
- `ScoreRing` inner text (`JobCard.tsx`)
- Any score displayed in feed headers, KPI cards, or tooltips
- Score values shown in `MatchScorePanel` or analytics views
