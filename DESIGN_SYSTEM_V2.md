# JobApply Design System V2: 'Meridian'

> **Status:** V2 — supersedes `DESIGN_SYSTEM.md` ('Editorial Intercom') as the target language.
> V1 tokens remain valid during migration; §11 maps every V1 rule to its V2 evolution.
> Nothing in this document overrides the scoring rules in `CLAUDE.md` or `.ai_rules`.

---

## 1. Identity & Philosophy

**Meridian** is the design language of an AI-native career system — not a job board with a
chatbot bolted on. The name is the metaphor: a meridian is the line a navigator trusts to
cross an ocean. Every surface should communicate the same promise: *the system has already
done the hard analysis, honestly, and shows its work.*

Three laws govern every screen:

1. **Calm authority.** Deep, dark anchors and generous whitespace. The interface never
   shouts — high scores, verified evidence, and real signals do the talking.
2. **Luminous intelligence.** AI presence is rendered as *light* (glows, gradients,
   luminous accents) layered onto a calm base — never as boxes, robots, or sparkle-spam.
   Where the machine reasoned, the surface glows softly; where data is missing, the
   surface says so plainly (honest degradation is a brand behavior, not an error state).
3. **Boxless density.** Inherited from V1 and strengthened: data-dense workspaces rely on
   typography hierarchy, hairline borders, and whitespace — never nested card-in-card
   chrome. Depth is reserved for things that *float* (overlays, alerts, the AI layer).

**Emotional target:** the confidence of a private wealth dashboard, the pace of a modern
IDE, none of the desperation aesthetics of legacy job boards.

---

## 2. Color System

### 2.1 Principles

- **Strictly no corporate blue.** `#0A66C2` and the `blue-*` scale are forbidden as
  accents. *Single exception:* the LinkedIn **source badge** (`ja.linkedin`), a protected
  external brand constant per `.ai_rules` source-labeling rules.
- **One brand, three voices:** Teal is the *product* (trust, progress). Amethyst is the
  *intelligence* (Ariel, AI reasoning, generated content). Emerald is *verification*
  (evidence-backed truth). They never swap roles — a user should be able to tell at a
  glance whether a surface is product chrome, machine reasoning, or verified fact.

### 2.2 Core tokens (Tailwind — extends the existing `ja.*` namespace)

| Role | Token | Hex | Notes |
|---|---|---|---|
| **Abyss** (dark anchor) | `ja.inkDeep` | `#0A1F1C` | Near-black teal. Hero/auth surfaces, dark headers, command overlays. Already in config. |
| **Harbor** (deep brand) | `ja.harbor` | `#134E4A` | teal-900. Authoritative fills, dark-surface buttons, active nav on dark. |
| **Primary** | `ja.primary` | `#0D9488` | teal-600. Unchanged from V1 — brand continuity is deliberate. |
| Primary hover | `ja.primaryHover` | `#0F766E` | teal-700. |
| Primary subtle | `ja.primarySubtle` | `#F0FDFA` | teal-50. Selected states, quiet fills. |
| **Amethyst** (AI voice) | `ja.ai` | `#7C3AED` | violet-600. Everything Ariel: chat identity, AI briefs, generated-content markers. Already the de-facto AI accent in code. |
| Amethyst subtle | `ja.aiSubtle` | `#F5F3FF` | violet-50. AI-surface fills, "AI wrote this" blocks. |
| Support accent | `ja.support` | `#4F46E5` | indigo-600. Eliya support chat only — keeps *help* visually distinct from *intelligence*. |
| **Electric Emerald** (verified) | `ja.verified` | `#10B981` | emerald-500. Live/verified signals, high-match pulses. |
| Success | `ja.success` | `#059669` | emerald-600. Unchanged. |
| Warn | `ja.warn` | `#D97706` | amber-600. Unchanged. |
| Danger | `ja.danger` | `#DC2626` | red-600. Unchanged. |
| Canvas | `ja.bg` | `#F8FAFC` | slate-50. Light workspace stays light — data density needs it. |
| Surface | `ja.surface` | `#FFFFFF` | Cards, panels. |
| Ink / text tiers | `ja.ink` / `ja.ink2` / `ja.muted` / `ja.subtle` | `#0F172A` / `#334155` / `#64748B` / `#94A3B8` | Unchanged. |
| Hairlines | `ja.line` / `ja.lineSoft` | `#E2E8F0` / `#F1F5F9` | Unchanged. |

### 2.3 Score bands (Match Score, Confidence Matrix — single source of truth)

All scores render at **1-decimal precision** (`.ai_rules`) with `tabular-nums`.

| Band | Range | Text/accent | Fill |
|---|---|---|---|
| Exceptional | ≥ 85.0 | `text-emerald-600` | `bg-emerald-50` |
| Strong | 70.0–84.9 | `text-teal-600` | `bg-teal-50` |
| Moderate | 50.0–69.9 | `text-amber-600` | `bg-amber-50` |
| Weak | 30.0–49.9 | `text-orange-600` | `bg-orange-50` |
| Poor / capped | < 30.0 | `text-slate-400` | `bg-slate-100` |

Thin-JD-capped scores (~28–30) intentionally land in the muted band — the visual system
reinforces the backend's honesty: an un-hydrated job *looks* unresolved, never exciting.

### 2.4 Gradients (used sparingly, only on AI and hero surfaces)

```css
--ja-gradient-intelligence: linear-gradient(135deg, #7C3AED 0%, #0D9488 100%);  /* Ariel identity */
--ja-gradient-abyss:        linear-gradient(180deg, #0A1F1C 0%, #134E4A 140%);  /* dark heroes */
--ja-glow-primary:          0 4px 20px rgba(13,148,136,0.40);                   /* FAB / CTA glow */
--ja-glow-ai:               0 4px 24px rgba(124,58,237,0.35);                   /* active AI surface */
--ja-glow-verified:         0 0 8px  rgba(16,185,129,0.45);                     /* live signal dot */
```

---

## 3. Surfaces, Depth & Glass

### 3.1 The three altitudes

| Altitude | What lives there | Treatment |
|---|---|---|
| **0 — Canvas** | Workspace, lists, data tables | `ja.bg`, no shadow, hairline separators |
| **1 — Cards** | JobCards, panels, kanban cards | `bg-white rounded-2xl border border-slate-100 shadow-elevation-1`; hover → `shadow-elevation-2` |
| **2 — Float** | Modals, Ariel overlay, dropdowns, toasts, FAB | `shadow-floating` + **glass** (below) |

Existing shadow tokens (`elevation-1`, `elevation-2`, `floating` in `tailwind.config.ts`)
are the canonical values — never inline flat `shadow-md`/`shadow-lg`.

### 3.2 Glass — transient layers only

Glassmorphism signals "this floats *above* your data and will leave." It is **only** for
altitude-2 transient surfaces; primary data cards stay opaque for readability.

```
/* Light glass — dropdowns, toasts, sticky sub-headers */
bg-white/85 backdrop-blur-xl border border-white/60 shadow-floating

/* Dark glass — command overlays, dark-hero flyouts */
bg-[#0A1F1C]/80 backdrop-blur-xl border border-white/10 text-white shadow-floating

/* Scrim behind modals/overlays */
bg-slate-900/55 backdrop-blur-[4px]
```

❌ Never glass on JobCards, tables, resumes, or anything the user reads for > 5 seconds.

### 3.3 Radii (unchanged from V1 — they were right)

`rounded-2xl` cards & modals · `rounded-lg` buttons & inputs · `rounded-full` only for
status dots and tiny badges — **never** navigation or primary actions.

---

## 4. Typography & Data Density

**Family:** Inter (existing). **Numerals:** every score, salary, count, and date column
uses `tabular-nums` — non-negotiable for scan-ability of dense match data.

| Tier | Usage | Classes |
|---|---|---|
| **Display** | Hero match score, headline metric | `text-[28px] font-bold tracking-tight tabular-nums` |
| Page heading | View titles | `text-[22px] font-semibold text-slate-900 tracking-tight` |
| Section label | Eyebrow labels | `text-[10.5px] font-bold tracking-widest uppercase text-slate-400` |
| Body | Card text, chat | `text-[13px] text-slate-700 leading-relaxed` |
| Data row | Constraint lists, JD requirements | `text-[12.5px] text-slate-700 tabular-nums` |
| Secondary | Meta, timestamps | `text-[12px] text-slate-500` |
| Micro | Badges, deltas | `text-[10px] font-semibold` |
| Code / keys | Env vars, ATS keys | `font-mono text-[11px] bg-slate-100 px-1 py-0.5 rounded` |

**Density rules for complex data** (JD constraints, resumes, score breakdowns):
- Max line length ~68ch for prose; constraint/requirement lists go full-width two-column.
- Separate rows with `divide-y divide-slate-50`, never boxes.
- Bilingual/RTL: mixed Hebrew/English blocks use `[unicode-bidi:plaintext] text-start`
  (already the ArielChat convention) so mixed-direction JD text never scrambles.

---

## 5. Layout & Navigation (carried forward, unchanged)

- Workspace: full-bleed fluid to `max-w-[1920px] mx-auto`.
- Nav tabs: plain text + `border-b-2` underline for active (`border-slate-900` on light,
  `border-teal-300` on Abyss). Never boxed, never pills, never `ring-*`.
- On dark (Abyss) headers: inactive tabs `text-slate-400`, active `text-white`.

---

## 6. AI-Native Patterns

The heart of V2. Every AI surface follows one contract: **amethyst voice, evidence
shown, confidence declared, honesty over theater.**

### 6.1 Ariel presence & chat overlay

- **Entry:** on-demand only — contextual buttons or the bottom-right FAB
  (teal fill, `--ja-glow-primary`). Never a persistent split-screen panel (V1 law, kept).
- **Overlay:** light-glass panel, `rounded-2xl`, slides from right
  (`transition-transform duration-250 ease-out`).
- **Identity:** Ariel's avatar dot uses `--ja-gradient-intelligence`; her message
  bubbles are `bg-white border border-slate-100`; *user* bubbles `bg-ja-primarySubtle`.
- **Streaming:** three-dot typing pulse in `ja.subtle`; streamed text has **no** shimmer
  overlays — the words arriving are the animation.
- **Generated-content marker:** anything Ariel *wrote into the user's world* (profile
  edits, CV bullets) carries a 2px amethyst left border + `bg-ja-aiSubtle` — the user
  can always see the machine's fingerprints.

### 6.2 Match Score visualization

- **Hero number:** Display tier, band color (§2.3), always 1 decimal ("87.4").
  On first render, count up from 0 over 600ms `ease-out` — once, never on re-render.
- **Composition bar:** a single horizontal stacked bar showing the three components
  (local / semantic+management / ATS) in teal tints — proportions match the real
  weights; no fake donuts.
- **Culture delta chip** (Dynamic Matching Score): renders only when non-null —
  `+3.9 culture fit` in `bg-teal-50 text-teal-700` or `−2.8 culture fit` in
  `bg-amber-50 text-amber-700`, with `culture_note` as its tooltip. Never rendered
  when the backend sent `None` — absence of signal is displayed as absence.
- **Thin-JD state:** score in muted band + explicit label "Awaiting full description —
  provisional score." Never a spinner pretending to be analysis.

### 6.3 Confidence & evidence indicators (Trust Dashboard / Capabilities)

Visual weight maps to the backend's source-weight hierarchy — stronger evidence
literally looks more solid:

| Verification tier | Treatment |
|---|---|
| Verified (STAR / portfolio) | Solid `bg-emerald-50 text-emerald-700` badge + `--ja-glow-verified` dot |
| Certification / CV-parsed | Tinted `bg-teal-50 text-teal-700`, no glow |
| Chat-stated (self-assertion) | Outline only: `border border-slate-200 text-slate-600` |
| Unknown / missing | `border-dashed border-slate-200 text-slate-400` |

**Honest degradation:** incomplete profiles show a plain-language banner
("Confidence is partial — no verified evidence yet") in `bg-amber-50/60`, listing the
missing sections. Degraded scores are *rendered* degraded — never dressed up.

### 6.4 High-match alert (trigger → notification)

When a high-match trigger fires: bell dot pulses once (`animate-ping`, single
iteration) in `ja.verified`; the dropdown row leads with the band-colored score chip.
A glass toast (`bottom-6 center, slide-up 200ms`) may announce it — auto-dismiss 5s,
never modal, never interrupting typing.

### 6.5 Feedback loop (thumbs up/down)

- Idle: ghost icons `text-slate-300`, visible on card hover.
- Commit: chosen icon springs (`scale 1 → 1.25 → 1`, 250ms), fills teal (up) or
  slate-500 (down); the pair collapses to the single chosen state.
- If learning shifted a soft preference, a one-line glass toast explains it:
  "Noted — your matches will lean more startup-paced." Transparency over magic.

---

## 7. Motion & Micro-interactions

**Feel:** precise, damped, immediate. Nothing bounces for fun.

| Token | Value | Use |
|---|---|---|
| `duration-fast` | 150ms | hovers, color/opacity |
| `duration-base` | 200ms | lifts, reveals, toasts |
| `duration-panel` | 250–300ms | overlay slide, modal fade |
| Easing | `ease-out` | everything entering |
| | `ease-in` | everything leaving |

**Canonical behaviors** (already proven in `Overview.tsx` — now law):

- **Card hover lift:** `hover:-translate-y-px` + `elevation-1 → elevation-2`, 200ms.
- **Press:** `active:scale-[0.98]` on buttons, `active:scale-95` on FAB.
- **Ambient glow:** decorative blur blobs at `opacity-[0.08]`, hover `0.16` — light as
  atmosphere, never as content.
- **Chevron reveal:** `-translate-x-1 opacity-0 → translate-x-0 opacity-100` on group hover.
- **Skeletons:** `bg-slate-100 animate-pulse` in the exact geometry of the loaded state.
- **Reduced motion:** all of the above collapse to opacity-only under
  `motion-reduce:` variants.

---

## 8. Component Behaviors

- **Buttons:** primary = `bg-ja-primary text-white rounded-lg hover:bg-ja-primaryHover`
  + press scale; secondary = white + hairline; destructive = `text-rose-600` ghost until
  hover. Disabled = `opacity-40`, never gray-out recolor. Loading = inline spinner
  replacing the label, width preserved.
- **JobCard:** altitude-1 contract (V1 container classes unchanged); expanded state →
  `shadow-elevation-2`; score chip top-right in band color; source badge (LinkedIn blue
  allowed here only); thumbs pair bottom-right on hover.
- **Inputs:** `rounded-lg border-slate-200`, focus = `border-teal-400 ring-2
  ring-teal-500/20` (rings are for *focus*, never nav). Error = rose equivalents +
  12px helper line below, no toast for field errors.
- **Modals:** scrim (§3.2) + `rounded-2xl bg-white shadow-floating`, fade+scale-in 200ms.
  One modal at a time; stacking is a design failure.
- **Toasts:** glass, bottom-center, 5s, one at a time, queue silently.
- **Kanban:** drag = `opacity-40 scale-95` on origin; drop targets tint with their
  column accent; commit springs the card once.
- **Empty states:** one sentence of plain language + one primary action. No illustrations
  of people jumping.

---

## 9. Accessibility & Trust Floor

- WCAG AA minimum: 50/700-scale pairings (e.g. `bg-teal-50 text-teal-700`) are the
  approved badge recipe — keep to it.
- Every score communicated by color also carries the number (color-blind safety).
- Focus visible everywhere: `focus-visible:ring-2 ring-teal-500` (buttons/inputs only).
- Hebrew/RTL first-class: logical properties (`ps-*/pe-*`, `text-start`) in all new
  components; `[unicode-bidi:plaintext]` on mixed-language user content.
- AI transparency floor: no AI output is ever presented as the user's own words without
  the amethyst marker (§6.1); confidence and provenance are always one glance away.

---

## 10. Anti-Patterns (Forbidden)

All V1 prohibitions carry forward, plus new AI-era ones:

- ❌ Corporate blue (`#0A66C2`, `bg-blue-*`) as accent — LinkedIn source badge excepted
- ❌ Nested card-in-card for primary content
- ❌ `rounded-full` on nav tabs or primary actions · ❌ `ring-*` on navigation
- ❌ Flat `shadow-md`/`shadow-lg` — use `elevation-*`/`floating` tokens
- ❌ Persistent split-screen AI chat
- ❌ Glass on primary data surfaces (cards, tables, resumes)
- ❌ Amethyst for non-AI content, or teal/emerald for AI voice (voice-swapping)
- ❌ Fake AI theater: shimmer on static content, fake "thinking" delays, spinners
  disguised as analysis
- ❌ Dressing up degraded/thin-JD scores as confident results
- ❌ Score displays without 1-decimal precision or without `tabular-nums`
- ❌ Truncating experience arrays before passing to LLM (see `CLAUDE.md` — yes, this is
  a design-system rule too: honest data in, honest pixels out)

---

## 11. V1 → V2 Migration Map

V2 is **additive**. Every V1 token remains valid; V2 formalizes what the codebase
already does and layers the AI-native system on top.

| V1 ('Editorial Intercom') | V2 ('Meridian') |
|---|---|
| Teal `#0D9488` primary | **Unchanged** — brand anchor |
| Slate canvas/ink/hairlines | **Unchanged** |
| `elevation-1/2`, `floating` shadows | **Unchanged**, now bound to the three-altitude model (§3.1) |
| Boxless, radii, nav rules | **Unchanged**, restated as law |
| Ad-hoc violet on AI surfaces | Formalized as `ja.ai` amethyst voice (§2.2, §6) |
| Ad-hoc indigo Eliya theme | Formalized as `ja.support` |
| `inkDeep` used only in auth hero | Promoted to **Abyss** dark-anchor tier (§2.2) |
| No glass rules | Glass contract for transient layers only (§3.2) |
| No score-band standard | Score bands + 1-decimal + `tabular-nums` law (§2.3, §4) |
| No AI interaction patterns | Full §6 suite (Ariel, score viz, confidence, alerts, feedback) |
| Motion implicit in code | Tokenized in §7 |

**Config additions required** (one-time, `tailwind.config.ts`): `ja.harbor`, `ja.ai`,
`ja.aiSubtle`, `ja.support`, `ja.verified` color tokens; gradient/glow CSS variables in
`globals.css`. No existing class in the codebase breaks.
