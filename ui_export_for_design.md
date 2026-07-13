# UI Export for Design Review

> Auto-generated snapshot of the core frontend files for the JobApply web dashboard.

## `web_dashboard/src/components/JobFeed.tsx`

_Job Dashboard / Feed layout_

```tsx
'use client'
import { useState, useEffect, useCallback, useMemo } from 'react'
import { TOKENS } from '@/lib/tokens'
import type { ApiFeedJob, JobSourceType, JobStatus } from '@/lib/apiTypes'
import type { Job, ReasonKind, AutomationSettings, WorkMode, Region, CompanyStage } from '@/lib/data'
import { fetchFeedJobs, forceRefreshAllScores, updateJobStatus, backfillJdText, startAnalysis, setAuthToken } from '@/lib/api'
import { supabase } from '@/lib/supabase'
import { JobCard } from './JobCard'
import { ApplierPreview } from './ApplierPreview'

// ── Preference filter helpers (client-side, Matches page only) ─────────────────

/**
 * Keyword sets for work-mode detection on free-form location / title strings.
 * These are applied client-side because backend location strings are unstructured.
 */
const WORK_MODE_KEYWORDS: Record<WorkMode, string[]> = {
  remote: ['remote', 'wfh', 'work from home', 'fully remote', 'full remote'],
  hybrid: ['hybrid'],
  onsite: [],  // "onsite" = not remote AND not hybrid
}

const REGION_KEYWORDS: Record<Region, string[]> = {
  'tel-aviv':  ['tel aviv', 'tlv', 'tel-aviv', 'jaffa', 'yafo'],
  central:     ['rishon', 'lod', 'ramla', 'rehovot', 'petah tikva', 'petach tikva',
                'holon', 'bat yam', 'ramat gan', 'givatayim', 'bnei brak', 'central'],
  sharon:      ['herzliya', "ra'anana", 'raanana', 'netanya', 'kfar saba', 'hod hasharon',
                'even yehuda', 'sharon'],
  haifa:       ['haifa', 'hadera', 'tirat carmel', 'krayot'],
  jerusalem:   ['jerusalem', 'yerushalayim', 'modiin', 'mevasseret'],
  south:       ['beer sheva', "be'er sheva", 'beersheba', 'eilat', 'ashdod',
                'ashkelon', 'kiryat gat'],
}

/** Company-stage heuristics on job title / company name strings. */
const STAGE_KEYWORDS: Record<CompanyStage, string[]> = {
  startup:    ['startup', 'start-up', 'seed', 'pre-seed', 'series a', 'stealth'],
  growth:     ['series b', 'series c', 'series d', 'scale', 'scaleup', 'growth stage'],
  enterprise: ['enterprise', 'corp', 'global', 'fortune', 'public company', 'listed'],
}

function locLower(job: ApiFeedJob): string {
  return (job.location ?? '').toLowerCase()
}
function titleLower(job: ApiFeedJob): string {
  return (job.title ?? '').toLowerCase() + ' ' + (job.company ?? '').toLowerCase()
}

function jobMatchesWorkMode(job: ApiFeedJob, modes: WorkMode[]): boolean {
  if (modes.length === 0) return true
  const loc   = locLower(job)
  const isRemote = WORK_MODE_KEYWORDS.remote.some(k => loc.includes(k))
  const isHybrid = WORK_MODE_KEYWORDS.hybrid.some(k => loc.includes(k))
  const isOnsite = !isRemote && !isHybrid

  return modes.some(m => {
    if (m === 'remote') return isRemote
    if (m === 'hybrid') return isHybrid
    if (m === 'onsite') return isOnsite
    return false
  })
}

function jobMatchesRegion(job: ApiFeedJob, regions: Region[]): boolean {
  if (regions.length === 0) return true
  const loc = locLower(job)
  return regions.some(r => REGION_KEYWORDS[r].some(k => loc.includes(k)))
}

function jobMatchesStage(job: ApiFeedJob, stages: CompanyStage[]): boolean {
  if (stages.length === 0) return true
  const text = titleLower(job)
  return stages.some(s => STAGE_KEYWORDS[s].some(k => text.includes(k)))
}

/** Returns true if the job should be shown given the current preferences. */
function passesPreferences(job: ApiFeedJob, prefs: AutomationSettings): boolean {
  // min_score is enforced server-side; repeat client-side as safety net
  if (prefs.minScore > 0 && job.match_score < prefs.minScore) return false
  if (!jobMatchesWorkMode(job, prefs.workModes))     return false
  if (!jobMatchesRegion(job,   prefs.regions))       return false
  if (!jobMatchesStage(job,    prefs.companyStages)) return false
  return true
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function toJob(f: ApiFeedJob, rank: number): Job {
  return {
    id:         f.job_id,
    title:      f.title,
    company:    f.company,
    location:   f.location,
    postedAt:   f.posted_at,
    postedRank: rank,
    // Always use match_score (the LLM-enriched composite) — never f.score,
    // which is the stale s1 local proxy value stored in the `score` DB column
    // and is never updated by the two-phase scoring pipeline.
    score:      f.match_score,
    isNew:      f.is_new,
    reasons:    f.reasons.map(r => ({ kind: r.kind as ReasonKind, label: r.label })),
    whyRon:     f.why_ron,
  }
}

const PAGE_SIZE = 50

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      style={{ animation: 'spin 0.8s linear infinite' }}
    >
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.25" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, tone = 'success' }: { message: string; tone?: 'success' | 'error' }) {
  return (
    <div
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-xl shadow-floating text-[13px] font-medium text-white"
      style={{ background: tone === 'success' ? TOKENS.color.success : TOKENS.color.danger }}
    >
      {message}
    </div>
  )
}

// ── Search bar ────────────────────────────────────────────────────────────────

function SearchBar({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="relative">
      <svg
        className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
        width={14} height={14} viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <input
        type="text"
        placeholder="Search by title or company…"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full h-9 pl-8 pr-8 rounded-lg border border-slate-200 bg-white text-[13px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/30 focus:border-teal-400 transition"
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          aria-label="Clear search"
        >
          <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2.5" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      )}
    </div>
  )
}

// ── Source filter chips ───────────────────────────────────────────────────────

type SourceFilter = 'all' | JobSourceType

const SOURCE_CHIP_OPTIONS: { id: SourceFilter; label: string }[] = [
  { id: 'all',          label: 'All Sources'    },
  { id: 'company_site', label: '🏢 Company Sites' },
  { id: 'linkedin',     label: '💼 LinkedIn'      },
  { id: 'other',        label: 'Other'            },
]

function SourceChips({
  active,
  setActive,
}: {
  active:    SourceFilter
  setActive: (s: SourceFilter) => void
}) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {SOURCE_CHIP_OPTIONS.map(opt => (
        <button
          key={opt.id}
          onClick={() => setActive(opt.id)}
          className={`h-7 px-2.5 rounded-full text-[11.5px] font-medium transition ${
            active === opt.id
              ? 'bg-slate-900 text-white'
              : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-800'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ── Status filter tabs ────────────────────────────────────────────────────────

type StatusFilter = 'all' | JobStatus

const STATUS_TABS: { id: StatusFilter; label: string }[] = [
  { id: 'all',     label: 'All'     },
  { id: 'new',     label: 'New'     },
  { id: 'saved',   label: 'Saved'   },
  { id: 'applied', label: 'Applied' },
  { id: 'ignored', label: 'Skipped' },
]

// ── Sort toggle ───────────────────────────────────────────────────────────────

type SortBy = 'score' | 'date'

function SortToggle({ value, onChange }: { value: SortBy; onChange: (v: SortBy) => void }) {
  return (
    <div className="flex items-center gap-0.5 rounded-full border border-slate-200 p-0.5 bg-white text-[11.5px]">
      {(['score', 'date'] as SortBy[]).map(v => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className={`h-6 px-2.5 rounded-full font-medium transition ${
            value === v
              ? 'bg-slate-900 text-white'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          {v === 'score' ? 'ATS Score' : 'Newest'}
        </button>
      ))}
    </div>
  )
}

// ── Top Fits toggle ───────────────────────────────────────────────────────────

const TOP_FITS_THRESHOLD = 60.0

function TopFitsToggle({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      title={active ? 'Showing top fits only (ATS score > 60)' : 'Show all scores'}
      className={`inline-flex items-center gap-1.5 h-7 px-3 rounded-full text-[11.5px] font-semibold transition ${
        active
          ? 'bg-emerald-600 text-white shadow-sm'
          : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-800'
      }`}
    >
      {active ? '✦' : '◇'} Top Fits
    </button>
  )
}

// ── JobFeed ───────────────────────────────────────────────────────────────────

interface JobFeedProps {
  /**
   * Called after a Force Refresh completes so the parent (page.tsx) can
   * re-fetch the Overview stats from the same data pool.
   */
  onFeedRefreshed?: () => void
  /**
   * Current user preferences — used to filter the Matches feed.
   * Analytics is untouched; only this component reads preferences.
   */
  preferences?: AutomationSettings
  /**
   * job_id to auto-expand on first render — set when the user clicks a
   * Top Matches row on the Overview tab.
   */
  expandJobId?: string
  /** Passed to each JobCard to enable Ariel Insight probes. */
  userId?: string
}

export function JobFeed({ onFeedRefreshed, preferences, expandJobId, userId }: JobFeedProps = {}) {
  const [jobs,         setJobs]         = useState<ApiFeedJob[]>([])
  // Raw count before the zero-click completeness filter — distinguishes
  // "pipeline still running" (totalFetched > 0, jobs === 0) from
  // "genuinely no rows yet" (totalFetched === 0).
  const [totalFetched, setTotalFetched] = useState(-1)  // -1 = not yet loaded
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState('')
  const [status,     setStatus]     = useState<StatusFilter>('all')
  const [search,     setSearch]     = useState('')
  const [source,     setSource]     = useState<SourceFilter>('all')
  const [sortBy,     setSortBy]     = useState<SortBy>('score')
  const [topFitsOnly,setTopFitsOnly]= useState(false)
  const [pageEnd,    setPageEnd]    = useState(PAGE_SIZE)
  const [syncing,          setSyncing]          = useState(false)
  const [jobUrl,           setJobUrl]           = useState('')
  const [isAnalyzing,      setIsAnalyzing]      = useState(false)
  const [toast,            setToast]            = useState<{ message: string; tone: 'success' | 'error' } | null>(null)
  const [reviewJob,        setReviewJob]        = useState<{ feedJob: ApiFeedJob; job: Job } | null>(null)
  // Tracks the job_id returned by handleAnalyze so the card auto-expands on insert
  const [freshExpandId,    setFreshExpandId]    = useState<string | undefined>(undefined)

  // ── Interaction lock ────────────────────────────────────────────────────────
  // While any card is expanded or mid-fetch the list order is frozen so the
  // card stays in its visual position even after a score update.
  const [activeJobIds,      setActiveJobIds]      = useState<ReadonlySet<string>>(new Set())
  const [lockedOrder,       setLockedOrder]       = useState<string[] | null>(null)
  // Jobs whose score dropped below TOP_FITS_THRESHOLD while the card was open.
  // They remain visible (with a badge) until the next manual loadJobs().
  const [belowThresholdIds, setBelowThresholdIds] = useState<ReadonlySet<string>>(new Set())

  const sortLocked = activeJobIds.size > 0

  // Dismiss toast after 5 s — long enough to read rescore/backfill messages
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  const loadJobs = useCallback(async () => {
    setLoading(true)
    setError('')
    // Release any frozen order and threshold exceptions on every full reload
    setLockedOrder(null)
    setBelowThresholdIds(new Set())
    try {
      // Refresh the module-level auth token from the live Supabase session
      // before every fetch.  The token is a module-level variable in api.ts;
      // if AuthContext hasn't set it yet (cold mount race) the request would
      // go unauthenticated → 401 → _onAuthError → signOut → localStorage.clear()
      // → tab resets to 'overview'.  This one-liner closes that race window.
      if (supabase) {
        const { data: { session } } = await supabase.auth.getSession()
        if (session?.access_token) setAuthToken(session.access_token)
      }

      const data = await fetchFeedJobs(undefined, 100, {
        minScore: preferences?.minScore,
      })
      setTotalFetched(data.length)
      // Zero-Click contract: only render jobs that are fully processed.
      // Incomplete rows (missing title, company, score, or structured JD) are
      // pipeline artefacts that should never surface to the user.
      const complete = data.filter(j =>
        j.title?.trim() &&
        j.company?.trim() &&
        (j.match_score ?? 0) > 0 &&
        j.jd_structured?.trim()
      )
      setJobs(complete)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load jobs.')
    } finally {
      setLoading(false)
    }
  }, [preferences?.minScore])

  // Initial mount only — loadJobs is NOT in the dependency array intentionally.
  // Putting loadJobs here would re-fire on every preferences change because
  // useCallback recreates it, causing an infinite request loop.
  // Subsequent loads are explicit: Refresh button (handleSync) or user action.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadJobs() }, [])

  // Reset page when any filter changes
  useEffect(() => { setPageEnd(PAGE_SIZE) }, [status, search, source, sortBy, topFitsOnly])

  // Unified sync — manual trigger only (Sync Data button).
  // Step 1: backfill missing JDs. Step 2: rescore. Step 3: reload feed.
  // No setTimeout, no automatic re-triggers.
  const handleSync = useCallback(async () => {
    setSyncing(true)
    // Clear the current list immediately so the user sees a loading skeleton
    // instead of the old stale snapshot while the sync is in flight.
    setJobs([])
    setTotalFetched(-1)
    setLoading(true)
    try {
      // Same token-refresh guard as loadJobs — Sync Data can be clicked any
      // time, including right after login before the token has settled.
      if (supabase) {
        const { data: { session } } = await supabase.auth.getSession()
        if (session?.access_token) setAuthToken(session.access_token)
      }
      const res = await backfillJdText(50.0)
      const n   = res.queued
      await forceRefreshAllScores()
      await loadJobs()
      onFeedRefreshed?.()
      setToast({
        message: n > 0
          ? `Synced ${n} job description${n !== 1 ? 's' : ''} and re-scored all jobs.`
          : 'Re-scored all jobs against your latest profile.',
        tone: 'success',
      })
    } catch {
      setToast({ message: 'Sync failed. Please try again.', tone: 'error' })
    } finally {
      setSyncing(false)
    }
  }, [loadJobs, onFeedRefreshed])

  /**
   * Submit a single job URL for the Zero-Click blocking pipeline.
   *
   * POST /api/jobs/analyze blocks until scrape → structure → score completes,
   * then returns the fully-processed JobMatch.  The job is prepended directly
   * into local state — no loadJobs() call, no polling.
   */
  const handleAnalyze = useCallback(async () => {
    const url = jobUrl.trim()
    if (!url) return
    setIsAnalyzing(true)
    try {
      // POST /api/jobs/analyze blocks until fully processed and returns the
      // complete JobMatch (same shape as ApiFeedJob).  Prepend it directly
      // into local state — no re-fetch of the entire feed needed.
      const newJob = await startAnalysis(url)
      setJobUrl('')
      setJobs(prev => {
        // Guard against the cache-hit case returning a duplicate.
        const already = prev.some(j => j.job_id === newJob.job_id)
        return already ? prev : [newJob, ...prev]
      })
      // Auto-expand the new card so the user sees the analysis immediately.
      setFreshExpandId(newJob.job_id)
      setToast({ message: `"${newJob.title}" added to your feed (ATS ${newJob.match_score.toFixed(1)})`, tone: 'success' })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Analysis failed.'
      setToast({ message: msg, tone: 'error' })
    } finally {
      setIsAnalyzing(false)
    }
  }, [jobUrl])

  const handleSkip = useCallback(async (id: string) => {
    setJobs(prev => prev.map(j => j.job_id === id ? { ...j, status: 'ignored' } : j))
    try {
      await updateJobStatus(id, 'ignored')
    } catch {
      setJobs(prev => prev.map(j => j.job_id === id ? { ...j, status: 'new' } : j))
      setToast({ message: 'Could not skip job. Please try again.', tone: 'error' })
    }
  }, [])

  const handleSave = useCallback(async (id: string) => {
    const job       = jobs.find(j => j.job_id === id)
    const nextStatus: JobStatus = job?.status === 'saved' ? 'new' : 'saved'
    setJobs(prev => prev.map(j => j.job_id === id ? { ...j, status: nextStatus } : j))
    try {
      await updateJobStatus(id, nextStatus)
    } catch {
      const prevStatus = job?.status ?? 'new'
      setJobs(prev => prev.map(j => j.job_id === id ? { ...j, status: prevStatus as JobStatus } : j))
      setToast({ message: 'Could not update job. Please try again.', tone: 'error' })
    }
  }, [jobs])

  const handleTailorCV = useCallback((feedJob: ApiFeedJob) => {
    // Always re-read from jobs state rather than using the prop snapshot that
    // JobCard held at render time — guarantees the guard below sees the latest
    // status and jd_structured values, not a stale closure capture.
    const fresh = jobs.find(j => j.job_id === feedJob.job_id) ?? feedJob
    const rank  = jobs.findIndex(j => j.job_id === feedJob.job_id)

    const pipelineDone =
      (fresh.status === 'new' || fresh.score_is_proxy === false) &&
      !!fresh.jd_structured?.trim()

    if (!pipelineDone) {
      console.warn('[JobFeed] CV generation blocked — job not ready',
        { job_id: fresh.job_id, status: fresh.status, score_is_proxy: fresh.score_is_proxy, has_jd: Boolean(fresh.jd_structured) })
      return
    }

    setReviewJob({ feedJob: fresh, job: toJob(fresh, rank) })
  }, [jobs])

  /**
   * Called by each JobCard whenever its expanded/fetch state changes.
   * Drives the sort-lock: while any card is active the list order is frozen.
   */
  const handleInteractionChange = useCallback((jobId: string, active: boolean) => {
    setActiveJobIds(prev => {
      const next = new Set(prev)
      active ? next.add(jobId) : next.delete(jobId)
      return next
    })
  }, [])

  /**
   * Called by JobCard when the user confirms they applied.
   * Updates the local job status to 'applied' so it moves to the correct tab.
   */
  const handleMarkApplied = useCallback((jobId: string) => {
    setJobs(prev => prev.map(j =>
      j.job_id === jobId ? { ...j, status: 'applied' as const } : j
    ))
    setToast({ message: '✓ Marked as Applied. Visible in Applications board', tone: 'success' })
  }, [])

  // ── Local filtering + sorting (no extra API calls) ────────────────────────

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()

    let result = jobs.filter(j => {
      // Status tab
      if (status === 'all' && j.status === 'ignored') return false
      if (status !== 'all' && j.status !== status)   return false
      // Source chip
      if (source !== 'all' && j.source_type !== source) return false
      // Top Fits toggle — only show jobs with ATS score above threshold
      if (topFitsOnly && j.match_score <= TOP_FITS_THRESHOLD) return false
      // Text search on title + company
      if (q && !j.title.toLowerCase().includes(q) && !j.company.toLowerCase().includes(q)) return false
      // ── User preferences (Matches page only) ─────────────────────────────
      // min_score is already applied server-side; replicated here as safety net
      // work_modes, regions, company_stages are client-side keyword heuristics
      if (preferences && !passesPreferences(j, preferences)) return false
      return true
    })

    // Sort — always by match_score (LLM composite); never fall back to the
    // stale `score` column which holds the old MatcherAgent fit score.
    if (sortBy === 'score') {
      result = [...result].sort((a, b) => b.match_score - a.match_score)
    } else {
      // "Newest" — primary key is created_at ISO string; fall back to job_id
      // (lexicographically descending) for rows where created_at is null so
      // the sort is never a no-op on partially-populated feeds.
      result = [...result].sort((a, b) => {
        const ta = a.created_at ?? a.job_id
        const tb = b.created_at ?? b.job_id
        return tb.localeCompare(ta)
      })
    }

    return result
  }, [jobs, status, source, search, sortBy, topFitsOnly, preferences])

  // ── Sort-lock: capture / release frozen order ─────────────────────────────
  // Capture the current sorted order the moment the first card opens.
  // Release it when all cards close (sortLocked → false).
  useEffect(() => {
    if (sortLocked && lockedOrder === null) {
      // First card opened — freeze the current visible order
      setLockedOrder(filtered.map(j => j.job_id))
    } else if (!sortLocked && lockedOrder !== null) {
      // Last card closed — release the frozen order
      setLockedOrder(null)
    }
  // filtered intentionally excluded: we only want to capture at the transition,
  // not re-capture on every data update.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortLocked])

  // ── displayList: frozen-order list for rendering ─────────────────────────
  // When locked: reorder jobs by lockedOrder (positions stay, data stays fresh).
  // Below-threshold exceptions bypass the TopFits gate until next reload.
  // When unlocked: identical to filtered.
  const displayList = useMemo(() => {
    if (!lockedOrder) return filtered

    const jobById = new Map(jobs.map(j => [j.job_id, j]))
    const q       = search.trim().toLowerCase()

    return lockedOrder
      .map(id => jobById.get(id))
      .filter((j): j is ApiFeedJob => {
        if (!j) return false
        // Re-apply all filters — but TopFits gate honours the below-threshold exception set
        if (status === 'all' && j.status === 'ignored') return false
        if (status !== 'all' && j.status !== status)   return false
        if (source !== 'all' && j.source_type !== source) return false
        if (topFitsOnly && j.match_score <= TOP_FITS_THRESHOLD && !belowThresholdIds.has(j.job_id)) return false
        if (q && !j.title.toLowerCase().includes(q) && !j.company.toLowerCase().includes(q)) return false
        return true
      })
  }, [lockedOrder, filtered, jobs, status, source, search, topFitsOnly, belowThresholdIds])

  const visible     = displayList.slice(0, pageEnd)
  const hasMore     = displayList.length > pageEnd
  const totalShown  = visible.length

  return (
    <section className="w-full">
      <div className="max-w-4xl space-y-8">

        {/* ── Page heading + sync ───────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Top Matches for You</h1>
            <p className="text-sm text-slate-400 mt-1">
              Jobs scored against your profile and sorted by ATS match.
            </p>
          </div>
          <button
            onClick={handleSync}
            disabled={syncing || loading}
            title="Fetch missing job descriptions and re-score all jobs against your latest profile"
            className="shrink-0 inline-flex items-center gap-2 h-9 px-4 rounded-lg text-[13px] font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none"
          >
            {syncing ? <Spinner /> : (
              <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            )}
            {syncing ? 'Syncing…' : 'Sync Data'}
          </button>
        </div>

        {/* ── URL submission bar ────────────────────────────────────────────── */}
        <form onSubmit={e => { e.preventDefault(); handleAnalyze() }} className="flex gap-2">
          <input
            type="url"
            placeholder="Paste a job URL to analyse…"
            value={jobUrl}
            onChange={e => setJobUrl(e.target.value)}
            disabled={isAnalyzing}
            className="flex-1 h-9 px-3 rounded-lg border border-slate-200 bg-white text-[13px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/30 focus:border-teal-400 transition disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isAnalyzing || !jobUrl.trim()}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg text-[13px] font-medium text-white transition active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none"
            style={{ background: isAnalyzing ? '#94a3b8' : TOKENS.color.primary }}
          >
            {isAnalyzing ? <><Spinner size={13} /> Analysing…</> : 'Analyse'}
          </button>
        </form>

        {/* ── Filters row ───────────────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row gap-2.5">
          <div className="flex-1 min-w-0">
            <SearchBar value={search} onChange={setSearch} />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <SourceChips active={source} setActive={setSource} />
            <div className="h-5 w-px bg-slate-200 hidden sm:block" />
            <TopFitsToggle active={topFitsOnly} onToggle={() => setTopFitsOnly(v => !v)} />
          </div>
        </div>

        {/* ── Error banner ──────────────────────────────────────────────────── */}
        {error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 flex items-center justify-between">
            <p className="text-[13px] text-rose-700">
              <span className="font-medium">Could not load feed</span>
              <span className="text-rose-500">: {error}</span>
            </p>
            <button onClick={loadJobs} className="text-[12px] font-medium text-rose-700 underline underline-offset-2">
              Retry
            </button>
          </div>
        )}

        {/* ── Status tabs + sort + count ────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-4 text-sm font-medium text-slate-400">
            {STATUS_TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setStatus(t.id)}
                className={`pb-1 transition-colors ${
                  status === t.id
                    ? 'text-slate-900 border-b-2 border-slate-900'
                    : 'hover:text-slate-900'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <span className="text-[12px] text-slate-400 tabular-nums">
              {totalShown} of {displayList.length}
              {sortLocked && (
                <span
                  className="ml-1.5 inline-flex items-center gap-0.5 text-[10.5px] text-amber-600 font-medium"
                  title="Sort order is paused while a card is open."
                >
                  <svg width={9} height={9} viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                  Sort paused
                </span>
              )}
            </span>
            <SortToggle value={sortBy} onChange={v => { if (!sortLocked) setSortBy(v) }} />
          </div>
        </div>

        {/* ── Job list ──────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="space-y-8">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="bg-white rounded-2xl border border-slate-100 p-8"
                style={{
                  opacity: 1 - i * 0.18,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.02), 0 20px 40px rgba(0,0,0,0.03)',
                }}
              >
                <div className="flex justify-between items-start mb-6">
                  <div className="space-y-2 flex-1 pr-8">
                    <div className="h-5 w-64 rounded-lg bg-slate-100 animate-pulse" />
                    <div className="h-3.5 w-40 rounded bg-slate-100 animate-pulse" />
                  </div>
                  <div className="h-9 w-16 rounded-lg bg-slate-100 animate-pulse shrink-0" />
                </div>
                <div className="space-y-2 mb-8">
                  <div className="h-3.5 w-full rounded bg-slate-100 animate-pulse" />
                  <div className="h-3.5 w-4/5 rounded bg-slate-100 animate-pulse" />
                </div>
                <div className="flex gap-3">
                  <div className="h-11 w-28 rounded-lg bg-slate-100 animate-pulse" />
                  <div className="h-11 w-40 rounded-lg bg-slate-100 animate-pulse" />
                </div>
              </div>
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-2 text-slate-400">
            {/* Pipeline-indexing state: rows exist in DB but none are pipeline-complete yet */}
            {!search && !topFitsOnly && status === 'all' && jobs.length === 0 && totalFetched > 0 ? (
              <>
                <div className="flex items-center gap-2 mb-1">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                    stroke="#0D9488" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    style={{ animation: 'spin 1.4s linear infinite' }}
                  >
                    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                  </svg>
                  <span className="text-[13px] font-semibold text-teal-700">Agents are actively indexing fresh roles</span>
                </div>
                <p className="text-[12.5px] text-center text-slate-500 max-w-xs">
                  {totalFetched} job{totalFetched !== 1 ? 's' : ''} found in the pipeline.
                  Scoring and JD enrichment in progress. Results will appear here automatically.
                </p>
                <button
                  onClick={handleSync}
                  disabled={syncing}
                  className="mt-3 inline-flex items-center gap-1.5 h-8 px-4 rounded-lg text-[12px] font-medium border border-teal-200 bg-teal-50 text-teal-700 hover:bg-teal-100 transition disabled:opacity-50"
                >
                  {syncing ? <Spinner size={12} /> : null}
                  {syncing ? 'Syncing…' : 'Check for updates'}
                </button>
              </>
            ) : !search && !topFitsOnly && status === 'all' && totalFetched === 0 ? (
              /* Genuinely empty DB — no jobs at all yet */
              <>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                  className="text-slate-300"
                >
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  <line x1="8" y1="11" x2="14" y2="11" />
                </svg>
                <p className="text-[14px] font-medium text-slate-600">No jobs discovered yet</p>
                <p className="text-[13px] text-center text-slate-500 max-w-xs">
                  Agents are warming up. New roles will appear here once the first scraping cycle completes.
                </p>
              </>
            ) : (
              /* Filter returned nothing */
              <>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                  className="text-slate-300"
                >
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  <line x1="8" y1="11" x2="14" y2="11" />
                </svg>
                <p className="text-[14px] font-medium text-slate-600">No jobs found</p>
                <p className="text-[13px] text-center">
                  {search
                    ? `No results for "${search}". Try a different search term.`
                    : topFitsOnly
                      ? `No matches with ATS score above ${TOP_FITS_THRESHOLD}. Try disabling Top Fits.`
                      : `No jobs with status "${status}".`}
                </p>
              </>
            )}
            {(search || topFitsOnly) && (
              <div className="mt-2 flex items-center gap-3">
                {search && (
                  <button onClick={() => setSearch('')} className="text-[12.5px] font-medium text-teal-600 hover:underline">
                    Clear search
                  </button>
                )}
                {topFitsOnly && (
                  <button onClick={() => setTopFitsOnly(false)} className="text-[12.5px] font-medium text-teal-700 hover:underline">
                    Show all scores
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="space-y-8">
              {visible.map(j => (
                <JobCard
                  key={j.job_id}
                  job={j}
                  userId={userId}
                  isTopFit={j.match_score > TOP_FITS_THRESHOLD}
                  belowThreshold={belowThresholdIds.has(j.job_id)}
                  initialExpanded={expandJobId === j.job_id || freshExpandId === j.job_id}
                  onSkip={handleSkip}
                  onSave={handleSave}
                  onTailorCV={handleTailorCV}
                  onInteractionChange={handleInteractionChange}
                  onMarkApplied={handleMarkApplied}
                />
              ))}
            </div>

            {hasMore && (
              <div className="flex justify-center">
                <button
                  onClick={() => setPageEnd(p => p + PAGE_SIZE)}
                  className="inline-flex items-center gap-2 h-9 px-6 rounded-lg text-[13px] font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition active:scale-[0.97]"
                >
                  Load more
                  <span className="text-slate-400 tabular-nums text-[12px]">
                    +{Math.min(PAGE_SIZE, filtered.length - pageEnd)}
                  </span>
                </button>
              </div>
            )}
          </>
        )}

      </div>

      {/* Full CV PDF editor */}
      {reviewJob && (
        <ApplierPreview
          job={reviewJob.job}
          feedJob={reviewJob.feedJob}
          onClose={() => setReviewJob(null)}
          onApplied={id => {
            handleSave(id)
            setReviewJob(null)
          }}
        />
      )}

      {toast && <Toast message={toast.message} tone={toast.tone} />}
    </section>
  )
}

```

## `web_dashboard/src/components/JobCard.tsx`

_Job Card / Job Item component_

```tsx
'use client'
import { useState, useCallback, useEffect, useRef } from 'react'
import type { ApiFeedJob, JobSourceType, ReasonKind } from '@/lib/apiTypes'
import { markJobApplied, refreshFeedScores, fetchJobJd, ensureFreshToken, getAuthHeaders } from '@/lib/api'
import { ProbeModal, type ProbeState } from './TrustDashboard'

const IS_DEV = process.env.NODE_ENV === 'development'
import { SkillIcon, ExpIcon, LocIcon, WarnIcon } from './icons'
import { OutreachModal }    from './OutreachModal'
import { AtsKeywordsPanel } from './AtsKeywordsPanel'

// ── Chevron ───────────────────────────────────────────────────────────────────

function ChevronDown({ s = 14, flipped = false }: { s?: number; flipped?: boolean }) {
  return (
    <svg
      width={s} height={s} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
      style={{ transition: 'transform 250ms ease', transform: flipped ? 'rotate(180deg)' : 'none' }}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

// ── External link / LinkedIn icons ────────────────────────────────────────────

function ExternalLinkIcon({ s = 12 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    >
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  )
}

function LinkedInIcon({ s = 13 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="currentColor" aria-label="LinkedIn">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  )
}

// RTL detection no longer needed due to dir="auto"

// ── RTL-aware bullet & paragraph atoms ───────────────────────────────────────

function BulletItem({ text }: { text: string }) {
  return (
    <li
      dir="auto"
      className="flex items-start gap-2 text-[12px] leading-relaxed text-slate-600 [unicode-bidi:plaintext] text-start"
    >
      <span className="mt-[6px] shrink-0 h-[5px] w-[5px] rounded-full bg-slate-400" />
      <span className="flex-1" dir="auto">{text}</span>
    </li>
  )
}

function ParagraphBlock({ text, className = '' }: { text: string; className?: string }) {
  return (
    <p
      dir="auto"
      className={`text-[12px] leading-relaxed text-slate-600 [unicode-bidi:plaintext] text-start ${className}`}
    >
      {text}
    </p>
  )
}

// ── JD formatter (unchanged) ──────────────────────────────────────────────────

const _EXPLICIT_BULLET = /^\s*[•\-\*–◦▪▸→◆]\s+/
const _NUMBER_BULLET   = /^\s*\d{1,2}[.)]\s+/
const _EM_DASH_BULLET  = /^\s*—\s+\S/

const _ACTION_VERBS_LINE = new RegExp(
  '^(develop|build|work|manage|lead|create|ensure|define|collaborate|design|analyze|' +
  'implement|support|drive|own|partner|coordinate|conduct|provide|identify|execute|' +
  'maintain|evaluate|monitor|deliver|contribute|prepare|write|review|oversee|' +
  'facilitate|research|optimize|scale|launch|engage|improve|track|prioritize|' +
  'establish|help|assist|communicate|report|gather|test|validate|deploy|integrate|' +
  'transform|shape|influence|architect|spec|ship)\\s',
  'i'
)

const _VERB_IN_TEXT = new RegExp(
  '\\b(develop|build|work|manage|lead|create|ensure|define|collaborate|design|analyze|' +
  'implement|support|drive|coordinate|conduct|provide|identify|execute|maintain|evaluate|' +
  'monitor|deliver|contribute|write|review|research|optimize|deploy|integrate|validate|' +
  'prioritize|establish|communicate|gather|test|launch|engage|improve|track)\\b',
  'gi'
)

const _TECH_TERM = /\b(SQL|Python|JavaScript|TypeScript|JS|TS|React|Node|AWS|GCP|Azure|API|REST|JSON|HTML|CSS|Git|Docker|Kubernetes|CI|CD|ML|AI|NLP|SaaS|B2B|KPI|OKR|CRM|ERP|MBA|BSc|MSc|Jira|Figma|Sketch|Tableau|Looker|dbt|Snowflake|Redshift|Spark|Kafka|Redis|Postgres|MySQL|MongoDB|GraphQL|gRPC|Terraform|Agile|Scrum|Kanban|[A-Z]{2,6})\b/g

const _HEADING_KW = new RegExp(
  '^(about|requirements?|qualifications?|responsibilities|what you[\\u2019\']?ll|what we[\\u2019\']?re|' +
  'who you are|nice to have|preferred|skills|experience|education|benefits?|compensation|' +
  'the role|your role|about us|about the company|you will|you have|you bring|the ideal|' +
  'minimum|basic|additional|key|core|primary|essential|overview|summary|' +
  'job description|responsibilities and|position overview|role overview|' +
  'we are looking|we[\\u2019\']re looking|what you[\\u2019\']ll|perks|culture|mission)\\b',
  'i'
)

function isBulletLine(l: string): boolean {
  return _EXPLICIT_BULLET.test(l) || _NUMBER_BULLET.test(l) || _EM_DASH_BULLET.test(l)
}
function stripBullet(l: string): string {
  return l.replace(_EXPLICIT_BULLET, '').replace(_NUMBER_BULLET, '').replace(/^\s*—\s+/, '').trim()
}
function isVerbLine(l: string): boolean {
  const t = l.trim()
  return t.length > 10 && t.length < 180 && _ACTION_VERBS_LINE.test(t)
}
function isHeadingLine(l: string): boolean {
  const t = l.trim()
  if (!t || t.length > 90) return false
  if (t.endsWith(':') && t.length < 60) return true
  if (_HEADING_KW.test(t) && !t.includes('. ')) return true
  if (t === t.toUpperCase() && t.length >= 4 && t.length < 50 && /^[A-Z\s&/]+$/.test(t)) return true
  return false
}
function trySplitParagraph(text: string): string[] | null {
  if (text.length < 100) return null
  const techHits = (text.match(_TECH_TERM) ?? []).length
  _VERB_IN_TEXT.lastIndex = 0
  const verbHits = (text.match(_VERB_IN_TEXT) ?? []).length
  if (techHits + verbHits < 3) return null
  const semiParts = text.split(/;\s+/).map(s => s.trim()).filter(s => s.length > 5)
  if (semiParts.length >= 2) return semiParts
  const commaParts = text.split(/,\s+/).map(s => s.trim()).filter(s => s.length > 8)
  if (commaParts.length >= 3) {
    _VERB_IN_TEXT.lastIndex = 0
    const qualifying = commaParts.filter(p =>
      (p.match(_TECH_TERM) ?? []).length > 0 || _VERB_IN_TEXT.test(p)
    )
    _VERB_IN_TEXT.lastIndex = 0
    if (qualifying.length / commaParts.length >= 0.6) return commaParts
  }
  return null
}
function renderBulletList(items: string[], bkey: number): React.ReactNode {
  return (
    <ul key={bkey} className="space-y-1 mb-3">
      {items.map((item, j) => <BulletItem key={j} text={item} />)}
    </ul>
  )
}
function formatJdText(text: string): React.ReactNode {
  let src = text.trim().replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const nlCount   = (src.match(/\n/g) ?? []).length
  const semiCount = (src.match(/;\s/g) ?? []).length
  if (nlCount < 4 && semiCount >= 3) src = src.replace(/;\s*/g, '\n')
  const lines  = src.split('\n')
  const blocks: React.ReactNode[] = []
  let   i = 0, bkey = 0
  while (i < lines.length) {
    const line = lines[i], trimmed = line.trim()
    if (!trimmed) { i++; continue }
    if (isHeadingLine(line)) {
      blocks.push(
        <p key={bkey++} className="text-[10.5px] font-bold tracking-widest uppercase text-slate-400 mt-4 mb-1 first:mt-0">
          {trimmed.replace(/:$/, '')}
        </p>
      )
      i++; continue
    }
    if (isBulletLine(line)) {
      const items: string[] = []
      while (i < lines.length) {
        const l = lines[i]
        if (isBulletLine(l)) { items.push(stripBullet(l)); i++ }
        else if (!l.trim()) {
          const next = lines.slice(i + 1).find(x => x.trim())
          if (next && isBulletLine(next)) { i++; continue }
          break
        } else break
      }
      if (items.length > 0) blocks.push(renderBulletList(items, bkey++))
      continue
    }
    if (isVerbLine(line)) {
      const items: string[] = []
      while (i < lines.length) {
        const l = lines[i]
        if (isVerbLine(l) && !isHeadingLine(l)) { items.push(l.trim()); i++ }
        else if (!l.trim()) {
          const next = lines.slice(i + 1).find(x => x.trim())
          if (next && isVerbLine(next) && !isHeadingLine(next)) { i++; continue }
          break
        } else break
      }
      if (items.length > 0) blocks.push(renderBulletList(items, bkey++))
      continue
    }
    const paraLines: string[] = []
    while (i < lines.length && lines[i].trim() && !isBulletLine(lines[i]) && !isHeadingLine(lines[i]) && !isVerbLine(lines[i])) {
      paraLines.push(lines[i].trim()); i++
    }
    const para = paraLines.join(' ')
    if (!para) continue
    const splitItems = trySplitParagraph(para)
    if (splitItems) blocks.push(renderBulletList(splitItems, bkey++))
    else blocks.push(<ParagraphBlock key={bkey++} text={para} className="mb-3" />)
  }
  return blocks.length > 0 ? <>{blocks}</> : <ParagraphBlock text={text.trim()} />
}

// ── Source badge ──────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<JobSourceType, string> = {
  linkedin:     'LinkedIn',
  company_site: 'Company Site',
  other:        'Other',
}
// Tone pairs use the Tailwind 50/700 scale — same recipe as the "Strong Match"
// badge (teal-50/teal-700), so every badge shares one visual grammar and clears
// WCAG AA contrast on its subtle background.
const SOURCE_STYLES: Record<JobSourceType, string> = {
  linkedin:     'bg-blue-50 text-blue-700',
  company_site: 'bg-emerald-50 text-emerald-700',
  other:        'bg-slate-100 text-slate-600',
}
function SourceBadge({ type }: { type: JobSourceType }) {
  return (
    <span
      className={`inline-flex items-center h-[17px] px-1.5 rounded text-[10px] font-semibold tracking-wide ${SOURCE_STYLES[type]}`}
    >
      {SOURCE_LABELS[type]}
    </span>
  )
}

function DirectApplyBadge() {
  return (
    <span
      className="inline-flex items-center gap-0.5 h-[17px] px-1.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800"
      title="Apply directly on the company's careers page"
    >
      ⚡ Direct
    </span>
  )
}

// ── Gap / reason tags ─────────────────────────────────────────────────────────

const GAP_TONES: Record<ReasonKind, { cls: string; Icon: (p: { s?: number }) => JSX.Element }> = {
  skill: { cls: 'bg-emerald-50 text-emerald-700', Icon: SkillIcon },
  exp:   { cls: 'bg-teal-50 text-teal-700',       Icon: ExpIcon   },
  loc:   { cls: 'bg-violet-50 text-violet-700',   Icon: LocIcon   },
  neg:   { cls: 'bg-ja-dangerSubtle text-red-700', Icon: WarnIcon  },
}
function GapTag({ kind, label }: { kind: ReasonKind; label: string }) {
  const t = GAP_TONES[kind] ?? GAP_TONES.neg
  const { Icon } = t
  return (
    <span
      className={`inline-flex items-center gap-1 h-5 px-1.5 rounded-md text-[11px] font-medium ${t.cls}`}
    >
      <Icon s={10} />
      {label}
    </span>
  )
}

// ── Action button ─────────────────────────────────────────────────────────────

interface ActionBtnProps {
  onClick:    (e: React.MouseEvent) => void
  className?: string
  style?:     React.CSSProperties
  children:   React.ReactNode
  title?:     string
  disabled?:  boolean
}
function ActionBtn({ onClick, className = '', style, children, title, disabled }: ActionBtnProps) {
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg text-[12px] font-medium transition active:scale-[0.97] disabled:opacity-40 disabled:pointer-events-none ${className}`}
      style={style}
    >
      {children}
    </button>
  )
}

// ── Structured JD renderer ───────────────────────────────────────────────────
//
// Parses the LLM-produced JSON string from jd_structured and renders each
// section with appropriate headings and bullet lists.
//
// Returns { node, ok } so the caller can fall back to raw-text rendering when
// parsing fails rather than silently rendering nothing.

interface StructuredJd {
  company_details:  string
  role_overview:    string
  responsibilities: string[]
  requirements:     string[]
  advantages:       string[]
  additional_info:  string
}

function parseStructuredJd(jsonStr: string): StructuredJd | null {
  try {
    const parsed = JSON.parse(jsonStr)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as StructuredJd
    }
  } catch { /* fall through */ }
  return null
}

const STRUCTURED_SECTION_LABELS: { key: keyof StructuredJd; label: string }[] = [
  { key: 'company_details',  label: 'About the Company'   },
  { key: 'role_overview',    label: 'Role Overview'        },
  { key: 'responsibilities', label: 'Responsibilities'     },
  { key: 'requirements',     label: 'Requirements'         },
  { key: 'advantages',       label: 'Nice to Have'         },
  { key: 'additional_info',  label: 'Additional Info'      },
]

function StructuredJdPanel({ parsed }: { parsed: StructuredJd }) {
  const sections = STRUCTURED_SECTION_LABELS.filter(({ key }) => {
    const val = parsed[key]
    return Array.isArray(val) ? val.length > 0 : Boolean(val)
  })

  if (sections.length === 0) return null

  return (
    <div className="rounded-lg bg-white border border-slate-200 divide-y divide-slate-100"
      style={{ boxShadow: 'inset 0 2px 4px rgba(15,23,42,0.04)' }}
    >
      {sections.map(({ key, label }) => {
        const val = parsed[key]
        return (
          <div key={key} className="px-4 py-3">
            <p className="text-[10.5px] font-bold tracking-widest uppercase text-slate-400 mb-2">
              {label}
            </p>
            {Array.isArray(val) ? (
              <ul className="space-y-1.5">
                {(val as string[]).map((item, i) => (
                  <li key={i} dir="auto" className="flex items-start gap-2 text-[12.5px] leading-relaxed text-slate-700 [unicode-bidi:plaintext] text-start">
                    <span className="mt-[7px] shrink-0 h-[4px] w-[4px] rounded-full bg-slate-400" />
                    <span className="flex-1" dir="auto">{item}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p dir="auto" className="text-[12.5px] leading-relaxed text-slate-700 [unicode-bidi:plaintext] text-start">{val as string}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── JD panel ──────────────────────────────────────────────────────────────────

const JD_COLLAPSE_THRESHOLD = 900

interface JdPanelProps {
  text:           string
  expanded:       boolean
  onToggleExpand: () => void
  isHebrewLocale?: boolean
}
function JdPanel({ text, expanded, onToggleExpand, isHebrewLocale = false }: JdPanelProps) {
  const isLong   = text.length > JD_COLLAPSE_THRESHOLD
  return (
    <div>
      <div className="relative">
        <div
          className="overflow-y-auto rounded-lg bg-white border border-slate-200 p-4"
          dir="auto"
          style={{
            boxShadow: 'inset 0 2px 4px rgba(15,23,42,0.04)',
            maxHeight: isLong ? (expanded ? '60vh' : '16rem') : undefined,
            transition: 'max-height 300ms ease',
          }}
        >
          {formatJdText(text)}
        </div>
        {isLong && !expanded && (
          <div
            className="absolute bottom-0 left-0 right-0 h-12 pointer-events-none rounded-b-lg"
            style={{ background: 'linear-gradient(to bottom, transparent, white)' }}
          />
        )}
      </div>
      {isLong && (
        <button
          onClick={onToggleExpand}
          className="mt-1.5 inline-flex items-center gap-1 text-[11.5px] font-medium text-teal-600 hover:text-teal-800 transition"
        >
          <ChevronDown s={11} flipped={expanded} />
          {expanded ? 'Collapse' : 'See more'}
        </button>
      )}
    </div>
  )
}

// ── Agent Analysis box ────────────────────────────────────────────────────────
//
// Three visual states:
//   pending  — score_is_proxy=true OR why_ron absent: animated skeleton
//   ready    — substantive why_ron text: rendered analysis
//   (dev)    — Retry button appears in both pending states when IS_DEV=true

function AnalysisSkeleton() {
  return (
    <div
      className="rounded-lg px-4 py-4 space-y-2.5 bg-slate-50 border border-slate-200"
      aria-busy="true"
      aria-label="Generating analysis"
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-50 bg-ja-primary" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-ja-primary" />
        </span>
        <span className="text-[12px] font-medium text-ja-primary">
          Generating deep insights…
        </span>
      </div>
      {[70, 90, 55].map((w, i) => (
        <div
          key={i}
          className="h-2.5 rounded-full animate-pulse bg-slate-200"
          style={{ width: `${w}%`, animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  )
}

// Mirror of the backend constant — jobs retired after this many failures.
const ENRICHMENT_MAX_FAILURES = 3

function _isSubstantiveText(text: string): boolean {
  // Two conditions only — mirrors is_substantive_analysis() in feed_service.py.
  // The third "core strengths" check was removed because it matched the first
  // line of every valid analysis that uses the required template format
  // ("🟢 Core Strengths:\n• ..."), causing all good analyses to show as skeleton.
  return (
    text.length >= 50 &&
    !/^[^\w]*[\w\s]+:\s*$/.test(text)
  )
}

// Backend sentinel values — must match feed_service.py constants exactly.
const AUTH_WALL_SENTINEL  = '__auth_wall__'

function AnalysisUnavailable() {
  return (
    <div
      className="rounded-lg px-4 py-3 flex items-start gap-3 bg-ja-dangerSubtle border border-red-200"
    >
      <span className="text-[15px] mt-0.5" aria-hidden="true">⚠️</span>
      <div className="flex-1 min-w-0">
        <p className="text-[12.5px] font-semibold text-slate-700 mb-0.5">Manual analysis required</p>
        <p className="text-[12px] text-slate-500 leading-relaxed">
          The scraper couldn&apos;t hydrate this job after {ENRICHMENT_MAX_FAILURES} attempts.
          This is likely a bot-block or expired posting. Open the original listing to review manually.
        </p>
      </div>
    </div>
  )
}

function AnalysisAuthWall() {
  return (
    <div
      className="rounded-lg px-4 py-3 flex items-start gap-3 bg-ja-primarySubtle border border-teal-200"
    >
      <span className="text-[15px] mt-0.5" aria-hidden="true">🔒</span>
      <div className="flex-1 min-w-0">
        <p className="text-[12.5px] font-semibold text-slate-700 mb-0.5">LinkedIn session expired</p>
        <p className="text-[12px] text-slate-500 leading-relaxed">
          The scraper hit a LinkedIn login wall. The <code className="font-mono text-[11px]">li_at</code> cookie
          needs refreshing. Update <code className="font-mono text-[11px]">LINKEDIN_LI_AT</code> in{' '}
          <code className="font-mono text-[11px]">backend/.env</code>, delete the browser profile, and restart
          the server. This job will be retried automatically.
        </p>
      </div>
    </div>
  )
}

// ── Shared tiny spinner (used by both AnalyzeJobButton and ArielInsightButton) ─

function SpinnerTiny({ s = 13 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
      style={{ animation: 'spin 0.8s linear infinite', flexShrink: 0 }}
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

// ── Analyze Job Button ────────────────────────────────────────────────────────
//
// Replaces the match score in the collapsed row when jd_text is absent/thin
// (score_is_proxy=true AND jd_text < 300 chars). Clicking triggers the scraper
// for this specific job so the backend can hydrate it and run Phase B scoring.

function AnalyzeJobButton({ jobId }: { jobId: string }) {
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')

  async function handleClick(e: React.MouseEvent) {
    e.stopPropagation()
    if (state !== 'idle') return
    setState('loading')
    try {
      await fetchJobJd(jobId)
      setState('done')
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 3000)
    }
  }

  if (state === 'done') {
    return (
      <span className="text-[11px] font-medium text-teal-600 shrink-0">
        ✓ Queued
      </span>
    )
  }

  return (
    <button
      onClick={handleClick}
      disabled={state === 'loading'}
      className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-[11.5px] font-semibold shrink-0 bg-ja-primarySubtle text-ja-primary border border-teal-200 hover:bg-teal-100 transition active:scale-[0.97] disabled:opacity-50"
    >
      {state === 'loading' ? (
        <><SpinnerTiny s={11} /> Analyzing…</>
      ) : state === 'error' ? (
        <span className="text-red-500">Failed</span>
      ) : (
        <>⚡ Analyze Job</>
      )}
    </button>
  )
}

// ── Ariel Insight Button ─────────────────────────────────────────────────────
//
// Appears when the analysis is ready AND the job has negative reason tags
// (skill/keyword gaps). Clicking launches a STAR probe for the first missing
// skill found in the user's Confidence Matrix.

function ArielInsightButton({
  userId,
  skillName,
}: {
  userId: string
  skillName: string
}) {
  const [loading,    setLoading]    = useState(false)
  const [probeState, setProbeState] = useState<ProbeState | null>(null)
  const [error,      setError]      = useState<string | null>(null)

  async function handleClick() {
    if (loading || !userId) return
    setLoading(true)
    setError(null)
    try {
      // Guard both fetches below against the mount-time token race.
      await ensureFreshToken()
      // 1. Fetch trust entities to find the matching entity_id
      const trustRes = await fetch(`/api/profile/${userId}/trust-score`, {
        headers: getAuthHeaders(),
        cache:   'no-store',
      })
      if (!trustRes.ok) throw new Error(`Trust API: HTTP ${trustRes.status}`)
      const trust = await trustRes.json()
      const entities: Array<{ entity_id: string; name: string; confidence_score: number }> =
        trust.entities ?? []

      // Case-insensitive fuzzy match on skill name
      const needle = skillName.toLowerCase()
      const match  = entities.find(e =>
        e.name.toLowerCase().includes(needle) || needle.includes(e.name.toLowerCase())
      )
      if (!match) throw new Error(`No entity found for "${skillName}". Upload CV to add it.`)
      if (match.confidence_score >= 70) throw new Error(`"${match.name}" already has high confidence (${match.confidence_score.toFixed(0)}).`)

      // 2. Start the probe
      const probeRes = await fetch('/api/ariel/probe/start', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body:    JSON.stringify({ entity_id: match.entity_id }),
      })
      if (!probeRes.ok) {
        const body = await probeRes.json().catch(() => ({}))
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${probeRes.status}`)
      }
      const data = await probeRes.json()
      setProbeState({
        session_id:     data.session_id,
        entity_id:      data.entity_id,
        entity_name:    data.entity_name,
        turn:           1,
        question:       data.question,
        answers:        {},
        done:           false,
        flag_type:      null,
        new_confidence: null,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start probe.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="flex items-center gap-2 flex-wrap mt-2">
        <button
          onClick={handleClick}
          disabled={loading}
          className="inline-flex items-center gap-1.5 h-7 px-3 rounded-lg text-[11.5px] font-semibold bg-ja-primarySubtle text-ja-primary border border-teal-200 hover:bg-teal-100 transition active:scale-[0.97] disabled:opacity-50"
          title={`Strengthen your "${skillName}" evidence with Ariel`}
        >
          {loading ? <SpinnerTiny s={11} /> : <span aria-hidden="true">⚡</span>}
          Ariel Insight: {skillName}
        </button>
        {error && (
          <span className="text-[11px] text-amber-600">{error}</span>
        )}
      </div>
      {probeState && (
        <ProbeModal
          probe={probeState}
          onClose={() => setProbeState(null)}
          onDone={() => setProbeState(null)}
        />
      )}
    </>
  )
}

function AgentAnalysisBox({ job, userId }: { job: ApiFeedJob; userId?: string }) {
  const raw           = (job.why_ron ?? '').trim()
  const analysisReady = _isSubstantiveText(raw) && !job.score_is_proxy
  const hardFailed    = (job.enrichment_failures ?? 0) >= ENRICHMENT_MAX_FAILURES
  const isAuthWall    = job.status === 'auth_wall'

  // Detect skill gaps from structured reason tags (kind === 'neg')
  const negReasons = job.reasons.filter(r => r.kind === 'neg')

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <span aria-hidden="true">🤖</span>
        <span className="text-[10.5px] font-bold uppercase tracking-widest text-slate-400">
          Agent Analysis
        </span>
        {IS_DEV && !analysisReady && !hardFailed && !isAuthWall && (
          <span className="ml-auto text-[10px] text-amber-600 font-medium">
            [DEV] enrichment pending — check server logs
          </span>
        )}
      </div>

      {analysisReady ? (
        <>
          <div
            className="rounded-lg px-4 py-3 bg-slate-50 border border-slate-200"
          >
            <p dir="auto" className="text-[13px] text-slate-600 leading-relaxed max-w-3xl [unicode-bidi:plaintext] text-start">
              {raw}
            </p>
          </div>
          {/* Ariel Insight: one button per negative reason, shown when userId available */}
          {userId && negReasons.length > 0 && (
            <div className="space-y-1">
              {negReasons.map(r => (
                <ArielInsightButton key={r.label} userId={userId} skillName={r.label} />
              ))}
            </div>
          )}
        </>
      ) : isAuthWall ? (
        <AnalysisAuthWall />
      ) : hardFailed ? (
        <AnalysisUnavailable />
      ) : (
        <AnalysisSkeleton />
      )}
    </div>
  )
}

// ── JobCard ───────────────────────────────────────────────────────────────────
//
// UX Pattern: Accordion with clickable compact row.
//
// COLLAPSED (default):
//   Score ring · Title · Company · Location · Badges · Reason tags · Chevron
//   → The entire row is the click target. No action buttons visible.
//     Users scan the list quickly with zero visual noise.
//
// EXPANDED (on click):
//   ① AI Analysis box  — why_ron first; highest decision-relevance per word.
//   ② Action bar       — all CTAs appear only after the user signals intent.
//   ③ Job description  — full formatted JD; fetched inline if not yet stored.
//   ④ ATS keyword gap  — power-user detail, collapsed within the panel.
//
// Design rationale:
//   • Removing buttons from the collapsed row eliminates "button soup" across
//     a list of 50+ cards. Users scan title → score → tags to decide interest;
//     only then do they need actions.
//   • "Why Ron" is the most decision-relevant sentence the AI produces. Putting
//     it at the top of the expanded state gives it the prominence it deserves.
//   • Source link lives in the action bar (not a separate row) to reduce chrome.
//   • Smooth accordion animation (CSS grid 0fr → 1fr) avoids abrupt layout jump.

export interface JobCardProps {
  job:              ApiFeedJob
  userId?:          string
  isTopFit?:        boolean
  belowThreshold?:  boolean
  initialExpanded?: boolean
  onSkip:           (id: string) => void
  onSave:           (id: string) => void
  onTailorCV:       (job: ApiFeedJob) => void
  onInteractionChange?: (jobId: string, active: boolean) => void
  onMarkApplied?:   (jobId: string) => void
}

export function JobCard({
  job, userId, isTopFit = false, belowThreshold = false, initialExpanded = false,
  onSkip, onSave, onTailorCV, onInteractionChange, onMarkApplied,
}: JobCardProps) {
  const [showDetails,      setShowDetails]      = useState(initialExpanded)
  const [jdExpanded,       setJdExpanded]       = useState(false)
  const [showOutreach,     setShowOutreach]     = useState(false)
  const [showAtsPanel,     setShowAtsPanel]     = useState(false)
  const [isMarkingApplied, setIsMarkingApplied] = useState(false)
  // Seed from server state so a refresh doesn't show "Mark Applied" again
  // for a job that's already in the applied/submitted pipeline stage.
  const [markedApplied,    setMarkedApplied]    = useState(
    () => job.status === 'applied'
  )
  const cardRef = useRef<HTMLElement>(null)

  useEffect(() => {
    onInteractionChange?.(job.job_id, showDetails)
  }, [showDetails, job.job_id, onInteractionChange])

  useEffect(() => {
    if (initialExpanded && cardRef.current) {
      setTimeout(() => {
        cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 100)
    }
  }, [initialExpanded])

  const isDirect           = job.is_direct_application === true || job.source_type === 'company_site'
  const isSaved            = job.status === 'saved'
  // Server-authoritative applied state — button must be visible/enabled for
  // any job NOT already in the 'applied' pipeline stage, regardless of
  // apply_url presence or has_tailored_cv. ('submitted' is an ApplicationRow
  // /CRM-pipeline status, not a JobStatus — it doesn't apply to job.status.)
  const isAlreadyApplied   = job.status === 'applied'
  const isHebrewLocale     = job.locale === 'he'
  const parsedStructuredJd = job.jd_structured ? parseStructuredJd(job.jd_structured) : null
  const hasJD              = Boolean(parsedStructuredJd) || Boolean(job.jd_text && job.jd_text.trim().length > 80)

  const handleMarkApplied = useCallback(async () => {
    if (isMarkingApplied || markedApplied || isAlreadyApplied) return
    setIsMarkingApplied(true)
    try {
      await markJobApplied(job.job_id)
      setMarkedApplied(true)
      onMarkApplied?.(job.job_id)
    } catch { /* silently fail */ }
    finally { setIsMarkingApplied(false) }
  }, [isMarkingApplied, markedApplied, isAlreadyApplied, job.job_id, onMarkApplied])

  const handleToggleDetails = () => setShowDetails(v => !v)

  // Title / company direction handled by dir="auto"

  return (
    <article
      ref={cardRef}
      className={`bg-white rounded-2xl border transition-shadow duration-200 ${
        isDirect ? 'border-emerald-200' : 'border-slate-100'
      } ${showDetails ? 'shadow-elevation-2' : 'shadow-elevation-1'}`}
    >
      {/* Direct-apply teal accent bar */}
      {isDirect && (
        <div
          className="h-0.5 rounded-t-2xl"
          style={{ background: 'linear-gradient(90deg, var(--ja-success), var(--ja-primary))' }}
        />
      )}

      {/* ── Collapsed header row — always visible, click to expand ────────── */}
      <div
        role="button"
        tabIndex={0}
        aria-expanded={showDetails}
        aria-label={`${job.title} at ${job.company || 'Unknown Company'} — ${showDetails ? 'collapse' : 'expand'} details`}
        onClick={handleToggleDetails}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleToggleDetails() }
        }}
        className={`group px-6 py-5 flex items-center gap-4 cursor-pointer select-none transition-colors rounded-t-2xl ${
          showDetails ? 'bg-slate-50/50' : 'hover:bg-slate-50/60'
        }`}
      >
        {/* Title + meta */}
        <div className="flex-1 min-w-0" dir="auto" style={{ textAlign: 'start', unicodeBidi: 'plaintext' }}>
          <div className="flex items-center gap-2.5 flex-wrap">
            <h2 className="text-[15px] font-bold text-slate-900 tracking-tight">
              {job.is_new && (
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full align-middle mr-2 -translate-y-[2px] bg-ja-primary"
                  title="New"
                />
              )}
              {job.title}
            </h2>
            {job.match_score >= 75 && (
              <span className="bg-teal-50 text-teal-700 text-[11px] font-semibold px-2 py-0.5 rounded-lg ring-1 ring-inset ring-teal-600/20 shrink-0">
                Strong Match
              </span>
            )}
            {isDirect && <DirectApplyBadge />}
            {belowThreshold && (
              <span
                className="inline-flex items-center px-1.5 py-0.5 rounded-lg text-[10px] font-semibold shrink-0 bg-ja-warnSubtle text-amber-700"
              >
                ↓ Below threshold
              </span>
            )}
          </div>
          <p className="text-[12.5px] text-slate-400 mt-1" dir="auto" style={{ textAlign: 'start', unicodeBidi: 'plaintext' }}>
            {job.company || 'Unknown Company'}
            {job.location && <> · {job.location}</>}
            {job.posted_at && <> · <span className="tabular-nums">{job.posted_at}</span></>}
          </p>
        </div>

        {/* Score numeral — hidden and replaced with Analyze CTA when JD is absent */}
        {job.score_is_proxy && (!job.jd_text || job.jd_text.trim().length < 300) ? (
          <AnalyzeJobButton jobId={job.job_id} />
        ) : (
          <div className="flex items-baseline gap-0.5 shrink-0">
            <span className="text-2xl font-bold text-slate-900 tracking-tight tabular-nums">
              {job.match_score > 0 ? job.match_score.toFixed(1) : '—'}
            </span>
            <span className="text-[10px] font-semibold text-slate-400 ml-0.5">/100</span>
          </div>
        )}

        {/* Expand chevron — signals interactivity */}
        <div className="shrink-0 text-slate-300 transition-colors group-hover:text-slate-500">
          <ChevronDown s={15} flipped={showDetails} />
        </div>
      </div>

      {/* ── Accordion: snippet + gaps + actions + JD ─────────────────────── */}
      <div
        style={{
          display: 'grid',
          gridTemplateRows: showDetails ? '1fr' : '0fr',
          transition: 'grid-template-rows 280ms cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        <div style={{ overflow: 'hidden' }}>
          <div className="border-t border-slate-100 px-6 pt-6 pb-7 space-y-6">

            {/* ① Source badge row */}
            <div className="flex items-center gap-2 flex-wrap">
              <SourceBadge type={job.source_type} />
            </div>

            {/* ② Agent Analysis */}
            <AgentAnalysisBox job={job} userId={userId} />

            {/* ③ Primary action row */}
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={e => { e.stopPropagation(); onTailorCV(job) }}
                className="bg-ja-primary text-white text-xs font-semibold tracking-wide uppercase px-6 py-3 rounded-lg hover:bg-ja-primaryHover transition-colors shadow-sm active:scale-[0.97]"
              >
                Tailor CV
              </button>

              <button
                onClick={e => { e.stopPropagation(); setJdExpanded(v => !v) }}
                className="border border-slate-200 text-slate-600 text-xs font-semibold tracking-wide uppercase px-6 py-3 rounded-lg hover:bg-slate-50 transition-colors active:scale-[0.97]"
              >
                {jdExpanded ? 'Hide Description' : 'View Job Description'}
              </button>

              <ActionBtn
                onClick={e => { (e as React.MouseEvent).stopPropagation(); setShowOutreach(true) }}
                className="border border-violet-200 text-violet-700 bg-violet-50 hover:bg-violet-100"
              >
                Outreach
              </ActionBtn>

              {/* Secondary: source, save, skip */}
              <div className="flex items-center gap-2 ml-auto">
                {job.apply_url && (
                  <a
                    href={job.apply_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                    className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-[11.5px] font-semibold transition ${
                      job.source_type === 'linkedin'
                        ? 'border border-ja-linkedin/25 bg-ja-linkedin/5 text-ja-linkedin hover:border-ja-linkedin/50'
                        : 'border border-teal-200 bg-teal-50 text-teal-700 hover:bg-teal-100'
                    }`}
                  >
                    {job.source_type === 'linkedin' ? <LinkedInIcon s={12} /> : <ExternalLinkIcon s={11} />}
                    {job.source_type === 'linkedin' ? 'LinkedIn' : 'Listing'}
                  </a>
                )}

                <ActionBtn
                  onClick={e => { (e as React.MouseEvent).stopPropagation(); onSave(job.job_id) }}
                  className={isSaved
                    ? 'border border-slate-300 text-slate-900 bg-slate-50'
                    : 'border border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-50'
                  }
                >
                  {isSaved ? '✓ Saved' : 'Save'}
                </ActionBtn>

                <ActionBtn
                  onClick={e => { (e as React.MouseEvent).stopPropagation(); onSkip(job.job_id) }}
                  className="text-slate-400 hover:text-slate-700 hover:bg-slate-100 border border-transparent hover:border-slate-200"
                >
                  Skip
                </ActionBtn>

                {/*
                  Always rendered for any job not already applied/submitted.
                  No dependency on apply_url or has_tailored_cv — manual status
                  updates must work regardless of whether the scraper found a
                  direct application link or a CV has been tailored yet.
                */}
                <ActionBtn
                  onClick={e => { (e as React.MouseEvent).stopPropagation(); handleMarkApplied() }}
                  disabled={isMarkingApplied || isAlreadyApplied || markedApplied}
                  className={(markedApplied || isAlreadyApplied)
                    ? 'border border-emerald-300 bg-emerald-50 text-emerald-700'
                    : 'border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50'
                  }
                >
                  {(markedApplied || isAlreadyApplied)
                    ? '✓ Applied'
                    : isMarkingApplied ? 'Saving…' : '✓ Mark Applied'}
                </ActionBtn>
              </div>
            </div>

            {/* ⑤ Job description sub-panel */}
            <div
              style={{
                display: 'grid',
                gridTemplateRows: jdExpanded ? '1fr' : '0fr',
                transition: 'grid-template-rows 260ms cubic-bezier(0.4, 0, 0.2, 1)',
              }}
            >
              <div style={{ overflow: 'hidden' }}>
                <div className="pt-4 space-y-4">
                  <p className="text-[11px] font-bold tracking-widest uppercase text-slate-400">
                    Job Description
                  </p>
                  {hasJD ? (
                    parsedStructuredJd ? (
                      <StructuredJdPanel parsed={parsedStructuredJd} />
                    ) : job.jd_text ? (
                      <JdPanel
                        text={job.jd_text.trim()}
                        expanded={jdExpanded}
                        onToggleExpand={() => setJdExpanded(v => !v)}
                        isHebrewLocale={isHebrewLocale}
                      />
                    ) : null
                  ) : (
                    <p className="text-[12px] text-slate-400 italic">
                      No description available.
                      {job.apply_url && (
                        <> <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
                          className="underline text-teal-600 hover:text-teal-800">View original posting.</a></>
                      )}
                    </p>
                  )}

                  {/* ATS Keyword Gap Analysis */}
                  <div className="pt-3 border-t border-slate-100">
                    <button
                      onClick={e => { e.stopPropagation(); setShowAtsPanel(p => !p) }}
                      className="flex items-center gap-1.5 text-[12px] font-medium text-slate-500 hover:text-slate-800 transition"
                    >
                      <span className="text-[10px]">{showAtsPanel ? '▼' : '▶'}</span>
                      ATS Keyword Gap Analysis
                      {!hasJD && <span className="text-[10px] text-amber-500 ml-0.5">(fetch JD first)</span>}
                    </button>
                    {showAtsPanel && (
                      <div className="mt-2">
                        <AtsKeywordsPanel jobId={job.job_id} hasJd={hasJD} />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      {showOutreach && (
        <OutreachModal job={job} onClose={() => setShowOutreach(false)} />
      )}
    </article>
  )
}

```

## `web_dashboard/src/components/MatchScorePanel.tsx`

_Match Score / AI badge component_

```tsx
'use client'

import { TOKENS } from '@/lib/tokens'
import type { MatchScoreResult } from '@/lib/apiTypes'

// ── Colour helpers ────────────────────────────────────────────────────────────

function scoreColor(total: number): { fg: string; bg: string; ring: string } {
  if (total >= 75) return {
    fg:   'oklch(0.38 0.13 155)',
    bg:   'oklch(0.96 0.04 155)',
    ring: 'oklch(0.70 0.14 155)',
  }
  if (total >= 50) return {
    fg:   'oklch(0.45 0.14 60)',
    bg:   'oklch(0.97 0.04 80)',
    ring: 'oklch(0.75 0.14 80)',
  }
  return {
    fg:   TOKENS.color.danger,
    bg:   'oklch(0.97 0.02 25)',
    ring: 'oklch(0.70 0.16 25)',
  }
}

function scoreLabel(total: number): string {
  if (total >= 75) return 'Strong match'
  if (total >= 50) return 'Partial match'
  return 'Weak match'
}

// ── Circular gauge ────────────────────────────────────────────────────────────

function CircleGauge({
  total, fg, ring, isLoading,
}: { total: number; fg: string; ring: string; isLoading?: boolean }) {
  const R    = 28
  const circ = 2 * Math.PI * R
  const fill = circ * (1 - total / 100)
  // spinning arc covers ~25% of the circle
  const spinLen = circ * 0.25

  return (
    <svg width={72} height={72} viewBox="0 0 72 72" style={{ flexShrink: 0 }}>
      <style>{`
        @keyframes score-spin { to { transform: rotate(360deg); } }
      `}</style>
      {/* track */}
      <circle cx={36} cy={36} r={R} fill="none" stroke="#E2E8F0" strokeWidth={6} />

      {isLoading ? (
        /* spinning arc */
        <circle
          cx={36} cy={36} r={R}
          fill="none"
          stroke={ring}
          strokeWidth={6}
          strokeDasharray={`${spinLen} ${circ - spinLen}`}
          strokeLinecap="round"
          style={{
            transformOrigin: '36px 36px',
            animation: 'score-spin 0.9s linear infinite',
          }}
        />
      ) : (
        /* static progress arc */
        <circle
          cx={36} cy={36} r={R}
          fill="none"
          stroke={ring}
          strokeWidth={6}
          strokeDasharray={circ}
          strokeDashoffset={fill}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      )}

      {/* label */}
      <text
        x={36} y={38}
        textAnchor="middle"
        dominantBaseline="middle"
        style={{
          fontSize: isLoading ? '11px' : '13px',
          fontWeight: 700,
          fill: fg,
          fontFamily: 'system-ui, sans-serif',
          opacity: isLoading ? 0.45 : 1,
          transition: 'opacity 0.2s',
        }}
      >
        {isLoading ? '…' : `${total.toFixed(1)}%`}
      </text>
    </svg>
  )
}

// ── Sub-bar ───────────────────────────────────────────────────────────────────

function SubBar({
  label, value, max, fg,
}: { label: string; value: number; max: number; fg: string }) {
  const pct = Math.round((value / max) * 100)
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 10, color: TOKENS.color.muted }}>{label}</span>
        <span style={{ fontSize: 10, fontWeight: 600, color: TOKENS.color.ink2 }}>
          {Math.round(value)}/{max}
        </span>
      </div>
      <div style={{
        height: 4, borderRadius: 4,
        background: '#E2E8F0', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: fg,
          borderRadius: 4,
          transition: 'width 0.5s ease',
        }} />
      </div>
    </div>
  )
}

// ── Keyword chip ──────────────────────────────────────────────────────────────

function KeywordChip({ word }: { word: string }) {
  return (
    <span style={{
      display: 'inline-block',
      fontSize: 10,
      fontWeight: 500,
      padding: '2px 7px',
      borderRadius: 4,
      background: 'oklch(0.97 0.02 25)',
      color:      'oklch(0.50 0.15 25)',
      border:     '0.75px solid oklch(0.90 0.05 25)',
      whiteSpace: 'nowrap',
    }}>
      {word}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export interface MatchScorePanelProps {
  score:          MatchScoreResult
  isLoading?:     boolean
  /**
   * Pre-tailoring baseline job score (0-100).
   * The panel will never display a total lower than this value — tailoring
   * an optimized CV cannot logically score below the raw baseline.
   */
  baselineScore?: number
}

export function MatchScorePanel({ score, isLoading, baselineScore }: MatchScorePanelProps) {
  // Floor the displayed total at the baseline: the tailored CV is always at
  // least as strong as the candidate's raw profile for this role.
  const displayTotal = Math.max(score.total, baselineScore ?? 0)
  const { fg, bg, ring } = scoreColor(displayTotal)

  return (
    <div style={{
      borderRadius: 12,
      border: `1px solid ${TOKENS.color.line}`,
      background: bg,
      padding: '14px 16px',
      marginBottom: 14,
      opacity: isLoading ? 0.55 : 1,
      transition: 'opacity 0.2s',
    }}>
      {/* ── Header row ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
        <CircleGauge total={displayTotal} fg={fg} ring={ring} isLoading={isLoading} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 13, fontWeight: 700, color: fg, lineHeight: 1.2 }}>
            {scoreLabel(displayTotal)}
          </p>
          <p style={{ fontSize: 11, color: TOKENS.color.muted, marginTop: 2 }}>
            Optimized ATS score
          </p>
          {baselineScore != null && baselineScore > 0 && (
            <p style={{ fontSize: 10, color: TOKENS.color.muted, marginTop: 3, opacity: 0.8 }}>
              Boosted from your {baselineScore}% baseline fit
            </p>
          )}
          {score.llm_validated && (
            <span style={{
              display: 'inline-block', marginTop: 4,
              fontSize: 9.5, fontWeight: 600,
              padding: '1px 6px', borderRadius: 4,
              background: TOKENS.color.primarySoft,
              color: TOKENS.color.primary,
            }}>
              AI-validated
            </span>
          )}
        </div>
      </div>

      {/* ── Sub-dimension bars ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
        <SubBar label="Keyword overlap"    value={score.keyword_overlap}     max={40} fg={ring} />
        <SubBar label="Skills alignment"   value={score.skills_alignment}    max={35} fg={ring} />
        <SubBar label="Seniority match"    value={score.seniority_alignment} max={25} fg={ring} />
      </div>

      {/* ── Keywords successfully injected ── */}
      {score.matched_keywords.length > 0 && (
        <div>
          <p style={{
            fontSize: 10, fontWeight: 600,
            color: 'oklch(0.34 0.11 155)',
            marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.6px',
          }}>
            ✓ Keywords Injected
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 4px' }}>
            {score.matched_keywords.slice(0, 10).map(kw => (
              <span key={kw} style={{
                display: 'inline-block',
                fontSize: 10, fontWeight: 500,
                padding: '2px 7px', borderRadius: 4,
                background: 'oklch(0.96 0.04 155)',
                color:      'oklch(0.34 0.11 155)',
                border:     '0.75px solid oklch(0.85 0.07 155)',
                whiteSpace: 'nowrap',
              }}>
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Skills excluded (requires real experience to verify) ── */}
      {score.missing_keywords.length > 0 && (
        <div style={{ marginTop: score.matched_keywords.length > 0 ? 10 : 0 }}>
          <p style={{
            fontSize: 9.5, fontWeight: 600,
            color: TOKENS.color.muted,
            marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.5px',
          }}>
            Skills Excluded (Requires Experience)
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 3px' }}>
            {score.missing_keywords.slice(0, 8).map(kw => (
              <span key={kw} style={{
                display: 'inline-block',
                fontSize: 9.5, fontWeight: 400,
                padding: '1px 6px', borderRadius: 4,
                background: 'oklch(0.97 0.00 0)',
                color:      TOKENS.color.muted,
                border:     '0.75px solid oklch(0.92 0.00 0)',
                whiteSpace: 'nowrap',
              }}>
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

```

## `web_dashboard/src/components/ArielChat.tsx`

_Ariel overlay (chat panel)_

```tsx
'use client'

import {
  useState, useRef, useEffect, useCallback, memo,
  type KeyboardEvent, type ReactNode, type ChangeEvent,
} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm    from 'remark-gfm'
import { TOKENS }         from '@/lib/tokens'
import { ensureFreshToken, getAuthHeaders } from '@/lib/api'
import { useOnboarding }  from '@/contexts/OnboardingContext'
import { useChat }        from '@/contexts/ChatContext'

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  student:    'Student',
  junior:     'Junior',
  mid:        'Mid-Level',
  senior:     'Senior',
  management: 'Management',
}

// Per-role seniority levels from the onboarding preferences step.
const SENIORITY_LABELS: Record<string, string> = {
  junior:    'Junior',
  entry:     'Entry-Level',
  mid:       'Mid-Level',
  senior:    'Senior',
  lead:      'Lead',
  director:  'Director',
  executive: 'Executive',
}

const LINE_HEIGHT_PX    = 20   // matches leading-5 / text-[13px] in the widget
const MAX_LINES         = 4
const MAX_TEXTAREA_H    = LINE_HEIGHT_PX * MAX_LINES + 32  // 4 lines + py-4 (16px top + 16px bottom)
const BASE_TEXTAREA_H   = 44   // 1 line (20px) + py-3 (12px × 2) = 44px — no clipping
const SCROLL_THRESHOLD  = 80
const REPLY_SNIPPET_LEN = 80

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface FileAttachment {
  base64:     string   // raw base64 without the "data:…;base64," prefix
  mediaType:  string   // MIME type (image/*, video/*, application/pdf, etc.)
  previewUrl: string   // data URL for preview (images) or empty string
  name:       string
}

// Backwards-compat alias used by ChatMessage.image and consumeStream
type ImageAttachment = FileAttachment

const MAX_ATTACHMENTS   = 10
const MAX_FILE_SIZE_MB  = 5    // per-file ceiling
const MAX_TOTAL_SIZE_MB = 20   // cumulative ceiling across all queued attachments

// Approximate a decoded byte count from a base64 payload (4 chars ≈ 3 bytes).
// Used to size already-queued attachments, which store base64 but not raw size.
const approxBytesFromBase64 = (b64: string) => Math.floor(b64.length * 0.75)

/** Mirrors the ChatMessageSchema Pydantic model on the backend. */
export interface ChatMessage {
  id:                 string
  role:               'user' | 'assistant'
  content:            string
  isPinned?:          boolean
  translatedContent?: string
  replyContext?:      string
  image?:             ImageAttachment
  attachments?:       FileAttachment[]
}

/** Shape returned by GET /api/chat/history (list). */
interface SessionSummary {
  session_id:    string
  created_at:    string   // ISO-8601
  updated_at:    string
  preview:       string   // first user message truncated to 80 chars
  message_count: number
}

function makeId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return Math.random().toString(36).slice(2, 10)
}

function fmtDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// ─────────────────────────────────────────────────────────────────────────────
// API helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Strip raw base64 from images before persisting — individual images can be
 * hundreds of KB.  Swap the empty string for a proper upload URL in Phase 4.
 */
function serializeMessages(msgs: ChatMessage[]): ChatMessage[] {
  return msgs.map(m => ({
    ...m,
    image: m.image
      ? { ...m.image, base64: '' }   // keep metadata; drop payload
      : undefined,
  }))
}

/** POST /api/chat/history — fire-and-forget; never throws to the caller. */
async function syncSession(sessionId: string, messages: ChatMessage[]): Promise<void> {
  if (!sessionId || messages.length === 0) return
  try {
    await ensureFreshToken()
    await fetch('/api/chat/history', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body:    JSON.stringify({ session_id: sessionId, messages: serializeMessages(messages) }),
    })
  } catch (err) {
    console.warn('[Ariel] session sync failed:', err)
  }
}

/** GET /api/chat/history — returns [] on error. */
async function fetchSessionList(): Promise<SessionSummary[]> {
  try {
    await ensureFreshToken()
    const res = await fetch('/api/chat/history', { headers: getAuthHeaders() })
    if (!res.ok) return []
    return (await res.json()) as SessionSummary[]
  } catch {
    return []
  }
}

/** GET /api/chat/history/:id — returns null on error. */
async function fetchSessionMessages(sessionId: string): Promise<ChatMessage[] | null> {
  try {
    await ensureFreshToken()
    const res = await fetch(`/api/chat/history/${sessionId}`, { headers: getAuthHeaders() })
    if (!res.ok) return null
    const data = await res.json() as { messages: ChatMessage[] }
    return data.messages
  } catch {
    return null
  }
}

/** Translation stub — replace with real /api/chat/translate in Phase 4. */
async function mockTranslate(content: string): Promise<string> {
  await new Promise(r => setTimeout(r, 700))
  const snippet = content.length > 120 ? content.slice(0, 120) + '…' : content
  return `[Auto-translated]\n${snippet}`
}

/** Feedback stub — replace with real POST /api/chat/feedback in Phase 4. */
async function submitFeedback(id: string, content: string): Promise<void> {
  await new Promise(r => setTimeout(r, 400))
  console.info('[Ariel feedback] submitted', { messageId: id, preview: content.slice(0, 60) })
}

// ─────────────────────────────────────────────────────────────────────────────
// Icons
// ─────────────────────────────────────────────────────────────────────────────

function SpinnerIcon({ s = 16 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
      style={{ animation: 'ariel-spin 0.8s linear infinite', flexShrink: 0 }}>
      <style>{`@keyframes ariel-spin{to{transform:rotate(360deg)}}`}</style>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.25" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

function SendIcon({ s = 16 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function PaperclipIcon({ s = 15 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66L9.41 17.41a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  )
}

function HistoryIcon({ s = 14 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 .49-3.51" />
      <polyline points="12 7 12 12 15 15" />
    </svg>
  )
}

function CopyIcon()        { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> }
function CheckIcon()       { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg> }
function ReplyIcon()       { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg> }
function TranslateIcon()   { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/></svg> }
function PinIcon({ filled = false }: { filled?: boolean }) { return <svg width={13} height={13} viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"/></svg> }
function FlagIcon()        { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg> }
function TrashIcon()       { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg> }
function EditIcon()        { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> }
function RegenerateIcon()  { return <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/></svg> }
function StopIcon({ s = 15 }: { s?: number }) { return <svg width={s} height={s} viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2.5"/></svg> }

// ─────────────────────────────────────────────────────────────────────────────
// StreamingMarkdown (memoised — unchanged from Phase 2)
// ─────────────────────────────────────────────────────────────────────────────

const mdComponents = {
  h1: ({ children }: { children?: ReactNode }) => <p className="font-bold text-[13.5px] text-slate-900 mb-1">{children}</p>,
  h2: ({ children }: { children?: ReactNode }) => <p className="font-semibold text-[13px] text-slate-900 mb-1">{children}</p>,
  h3: ({ children }: { children?: ReactNode }) => <p className="font-semibold text-[12.5px] text-slate-800 mb-0.5">{children}</p>,
  p:  ({ children }: { children?: ReactNode }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }: { children?: ReactNode }) => <ul className="space-y-0.5 mb-2 pl-0">{children}</ul>,
  ol: ({ children }: { children?: ReactNode }) => <ol className="list-decimal pl-4 space-y-0.5 mb-2">{children}</ol>,
  li: ({ children }: { children?: ReactNode }) => (
    <li className="flex items-start gap-1.5">
      <span className="mt-[7px] shrink-0 w-[4px] h-[4px] rounded-full bg-slate-400" aria-hidden />
      <span className="flex-1">{children}</span>
    </li>
  ),
  strong: ({ children }: { children?: ReactNode }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  em:     ({ children }: { children?: ReactNode }) => <em className="italic text-slate-700">{children}</em>,
  code:   ({ children, className }: { children?: ReactNode; className?: string }) => {
    const isBlock = !!className?.startsWith('language-')
    return isBlock
      ? <code className="block bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-[11.5px] font-mono text-slate-700 overflow-x-auto mb-2 whitespace-pre">{children}</code>
      : <code className="bg-slate-100 rounded px-1 py-0.5 text-[11.5px] font-mono text-slate-700">{children}</code>
  },
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="border-l-2 border-teal-300 pl-3 italic text-slate-500 mb-2">{children}</blockquote>
  ),
  table: ({ children }: { children?: ReactNode }) => (
    <div className="overflow-x-auto mb-2">
      <table className="text-[11.5px] border-collapse w-full">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: ReactNode }) => <th className="border border-slate-200 px-2 py-1 bg-slate-50 font-semibold text-left">{children}</th>,
  td: ({ children }: { children?: ReactNode }) => <td className="border border-slate-200 px-2 py-1">{children}</td>,
  a:  ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a href={href} target="_blank" rel="noopener noreferrer"
      className="text-teal-600 underline underline-offset-2 hover:text-teal-700">{children}</a>
  ),
  hr: () => <hr className="border-slate-200 my-2" />,
}

const StreamingMarkdown = memo(function StreamingMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as never}>
      {content}
    </ReactMarkdown>
  )
})

// ─────────────────────────────────────────────────────────────────────────────
// MessageActionBar (unchanged from Phase 2)
// ─────────────────────────────────────────────────────────────────────────────

interface ActionBarCallbacks {
  onCopy:          () => void
  onReply:         () => void
  onTranslate:     () => void
  onPin:           () => void
  onReport:        () => void
  onDelete:        () => void
  onEdit?:         () => void   // user messages only
  onRegenerate?:   () => void   // latest assistant message only
  isPinned:        boolean
  isTranslating:   boolean
}

function MessageActionBar({ isUser, callbacks }: { isUser: boolean; callbacks: ActionBarCallbacks }) {
  // Brief "Copied!" feedback — swap the icon/label back after 2s. A ref holds
  // the timeout id so a rapid second click restarts the window instead of
  // stacking timeouts, and so it can be cleared on unmount.
  const [copied, setCopied]   = useState(false)
  const copiedTimeoutRef      = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => { if (copiedTimeoutRef.current) clearTimeout(copiedTimeoutRef.current) }, [])

  const handleCopy = useCallback(() => {
    callbacks.onCopy()
    setCopied(true)
    if (copiedTimeoutRef.current) clearTimeout(copiedTimeoutRef.current)
    copiedTimeoutRef.current = setTimeout(() => setCopied(false), 2000)
  }, [callbacks])

  const actions = [
    {
      icon:  copied ? <CheckIcon /> : <CopyIcon />,
      label: copied ? 'Copied!' : 'Copy',
      danger: false,
      fn: handleCopy,
    },
    { icon: <ReplyIcon />,   label: 'Reply',  danger: false, fn: callbacks.onReply  },
    // Edit — user messages only
    ...(isUser && callbacks.onEdit ? [{
      icon: <EditIcon />, label: 'Edit', danger: false, fn: callbacks.onEdit,
    }] : []),
    // Translate — assistant messages only
    ...(!isUser ? [{
      icon:  callbacks.isTranslating ? <SpinnerIcon s={13} /> : <TranslateIcon />,
      label: 'Translate', danger: false, fn: callbacks.onTranslate,
    }] : []),
    // Regenerate — latest assistant message only
    ...(!isUser && callbacks.onRegenerate ? [{
      icon: <RegenerateIcon />, label: 'Regenerate', danger: false, fn: callbacks.onRegenerate,
    }] : []),
    { icon: <PinIcon filled={callbacks.isPinned} />, label: callbacks.isPinned ? 'Unpin' : 'Pin', danger: false, fn: callbacks.onPin },
    { icon: <FlagIcon />,    label: 'Report', danger: false, fn: callbacks.onReport  },
    { icon: <TrashIcon />,   label: 'Delete', danger: true,  fn: callbacks.onDelete  },
  ]

  // Inline below the bubble — never clipped by overflow-y-auto.
  // Visibility is controlled by opacity via the parent group-hover.
  return (
    <div
      className={`
        flex items-center gap-0.5 px-0.5 py-0.5 mt-0.5
        opacity-0 group-hover:opacity-100 group-focus-within:opacity-100
        pointer-events-none group-hover:pointer-events-auto group-focus-within:pointer-events-auto
        transition-opacity duration-150
        ${isUser ? 'self-end' : 'self-start ml-9'}
      `}
      onMouseEnter={e => e.stopPropagation()}
    >
      {actions.map(a => (
        <button key={a.label} onClick={a.fn} title={a.label} aria-label={a.label}
          className={`
            w-6 h-6 flex items-center justify-center rounded-lg transition
            ${a.danger ? 'text-slate-300 hover:text-rose-500 hover:bg-rose-50' : 'text-slate-300 hover:text-slate-600 hover:bg-slate-100'}
            ${a.label === 'Unpin' || a.label === 'Copied!' ? '!text-teal-500' : ''}
          `}>
          {a.icon}
        </button>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MessageBubble (unchanged from Phase 2)
// ─────────────────────────────────────────────────────────────────────────────

interface BubbleProps {
  message:            ChatMessage
  isStreaming:        boolean
  showTranslation:    boolean
  isTranslating:      boolean
  isLatestAssistant:  boolean   // controls Regenerate visibility
  onDelete:           (id: string) => void
  onReply:            (msg: ChatMessage) => void
  onPin:              (id: string) => void
  onTranslate:        (id: string) => void
  onReport:           (id: string, content: string) => void
  onEdit:             (id: string) => void
  onRegenerate:       (id: string) => void
}

const MessageBubble = memo(function MessageBubble({
  message, isStreaming, showTranslation, isTranslating, isLatestAssistant,
  onDelete, onReply, onPin, onTranslate, onReport, onEdit, onRegenerate,
}: BubbleProps) {
  const isUser   = message.role === 'user'
  const rendered = showTranslation && message.translatedContent ? message.translatedContent : message.content

  const callbacks: ActionBarCallbacks = {
    isPinned:      !!message.isPinned,
    isTranslating,
    onCopy:        () => { navigator.clipboard.writeText(message.content).catch(() => {}) },
    onReply:       () => onReply(message),
    onTranslate:   () => onTranslate(message.id),
    onPin:         () => onPin(message.id),
    onReport:      () => onReport(message.id, message.content),
    onDelete:      () => onDelete(message.id),
    onEdit:        isUser                ? () => onEdit(message.id)       : undefined,
    onRegenerate:  isLatestAssistant     ? () => onRegenerate(message.id) : undefined,
  }

  return (
    // `group` here drives the hover-reveal of the action bar below
    <div className={`group flex flex-col ${isUser ? 'items-end' : 'items-start'} gap-0.5`}>
      {message.replyContext && (
        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] text-slate-500 bg-slate-100 border-l-2 border-slate-300 max-w-[85%] ${isUser ? 'self-end' : 'self-start ml-9'}`}>
          <ReplyIcon />
          <span className="truncate">{message.replyContext}</span>
        </div>
      )}
      {/* Bubble row */}
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} w-full`}>
        {!isUser && (
          <div className="w-7 h-7 rounded-full text-white text-[11px] font-bold flex items-center justify-center mr-2 mt-0.5 flex-shrink-0"
            style={{ background: TOKENS.color.primary }}>A</div>
        )}
        <div
          dir="auto"
          className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed transition-all duration-200 [unicode-bidi:plaintext] text-start
            ${isUser ? 'text-white rounded-tr-sm' : 'bg-white border text-slate-800 rounded-tl-sm'}
            ${!isUser && message.isPinned ? 'border-teal-300 bg-teal-50/40' : !isUser ? 'border-slate-100' : ''}
          `}
          style={isUser ? { background: TOKENS.color.primary } : undefined}
        >
          {message.isPinned && (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-teal-600 mb-1.5">
              <PinIcon filled /> Pinned
            </span>
          )}
          {isUser && message.attachments && message.attachments.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-1.5">
              {message.attachments.map((a, i) => {
                const dot  = a.name.lastIndexOf('.')
                const base = dot > 0 ? a.name.slice(0, dot) : a.name
                const ext  = dot > 0 ? a.name.slice(dot + 1) : ''
                const label = base.length > 12 ? `${base.slice(0, 10)}…${ext ? `.${ext}` : ''}` : a.name
                return (
                  <span key={i} className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-white/20 text-white/90 leading-none" title={a.name}>
                    <span className="font-semibold uppercase opacity-75 text-[9px]">{ext || '📎'}</span>
                    {label}
                  </span>
                )
              })}
            </div>
          )}
          {isUser
            ? <span className="whitespace-pre-wrap">{rendered}</span>
            : rendered ? <StreamingMarkdown content={rendered} /> : null
          }
          {!isUser && message.translatedContent && (
            <button onClick={() => onTranslate(message.id)}
              className="mt-1.5 block text-[10.5px] text-teal-500 hover:text-teal-700 transition">
              {showTranslation ? 'Show original' : 'Show translation'}
            </button>
          )}
          {isStreaming && !isUser && (
            <span className="inline-block w-[2px] h-[14px] bg-teal-500 ml-0.5 align-middle"
              style={{ animation: 'ariel-cursor 0.9s ease-in-out infinite' }} />
          )}
        </div>
      </div>
      {/* Action bar — inline below the bubble, revealed on group-hover */}
      <MessageActionBar isUser={isUser} callbacks={callbacks} />
      <style>{`@keyframes ariel-cursor{0%,100%{opacity:1}50%{opacity:0}}`}</style>
    </div>
  )
})

// ─────────────────────────────────────────────────────────────────────────────
// TypingIndicator (unchanged)
// ─────────────────────────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="w-7 h-7 rounded-full text-white text-[11px] font-bold flex items-center justify-center mr-2 mt-0.5 flex-shrink-0"
        style={{ background: TOKENS.color.primary }}>A</div>
      <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1">
        {[0, 1, 2].map(i => (
          <span key={i} className="w-1.5 h-1.5 rounded-full bg-slate-300"
            style={{ animation: `ariel-dot 1.2s ease-in-out ${i * 0.18}s infinite` }} />
        ))}
      </div>
      <style>{`@keyframes ariel-dot{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}`}</style>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// HistoryPanel — slides in over the message list
// ─────────────────────────────────────────────────────────────────────────────

interface HistoryPanelProps {
  isOpen:         boolean
  onClose:        () => void
  sessions:       SessionSummary[]
  loadingList:    boolean
  activeSessionId: string
  onSelectSession: (id: string) => void
  onNewSession:    () => void
}

function HistoryPanel({
  isOpen, onClose, sessions, loadingList, activeSessionId, onSelectSession, onNewSession,
}: HistoryPanelProps) {
  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="absolute inset-0 z-20 bg-black/10"
          onClick={onClose}
        />
      )}

      {/* Slide-in panel */}
      <div
        className={`
          absolute top-0 right-0 bottom-0 z-30 w-72
          bg-white border-l border-slate-100 shadow-floating
          flex flex-col
          transition-transform duration-250 ease-out
          ${isOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
      >
        {/* Panel header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 flex-shrink-0">
          <div className="flex items-center gap-2 text-slate-700">
            <HistoryIcon />
            <span className="text-[13px] font-semibold">History</span>
          </div>
          <button
            onClick={onClose}
            aria-label="Close history panel"
            title="Close"
            className="w-6 h-6 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 focus-visible:text-slate-700 transition text-[16px] leading-none"
          >×</button>
        </div>

        {/* New session shortcut */}
        <div className="px-3 py-2 border-b border-slate-100 flex-shrink-0">
          <button
            onClick={() => { onNewSession(); onClose() }}
            className="w-full text-left text-[12px] text-teal-600 font-medium px-3 py-2 rounded-lg hover:bg-teal-50 transition flex items-center gap-2"
          >
            <span className="text-[16px] leading-none">+</span> New conversation
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto">
          {loadingList ? (
            <div className="flex items-center justify-center h-24 text-slate-400">
              <SpinnerIcon s={18} />
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 gap-2 text-center px-6">
              <HistoryIcon s={20} />
              <p className="text-[12px] text-slate-400">No previous conversations yet.</p>
            </div>
          ) : (
            <ul className="p-2 space-y-1">
              {sessions.map(s => {
                const isActive = s.session_id === activeSessionId
                return (
                  <li key={s.session_id}>
                    <button
                      onClick={() => { onSelectSession(s.session_id); onClose() }}
                      className={`
                        w-full text-left px-3 py-2.5 rounded-xl transition
                        ${isActive
                          ? 'bg-teal-50 border border-teal-200'
                          : 'hover:bg-slate-50 border border-transparent'
                        }
                      `}
                    >
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[10.5px] text-slate-400">{fmtDate(s.updated_at)}</span>
                        <span className="text-[10px] text-slate-300">{s.message_count} msg{s.message_count !== 1 ? 's' : ''}</span>
                      </div>
                      <p dir="auto" className="text-[12px] text-slate-600 leading-snug line-clamp-2 [unicode-bidi:plaintext] text-start">{s.preview || 'Empty conversation'}</p>
                      {isActive && (
                        <span className="mt-1 inline-block text-[10px] font-semibold text-teal-600">Active</span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 1 hooks (unchanged)
// ─────────────────────────────────────────────────────────────────────────────

function useAutoHeight(ref: React.RefObject<HTMLTextAreaElement | null>, value: string) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    // Reset to 'auto' first so scrollHeight shrinks when text is deleted,
    // then let the browser measure the true content height.
    // min-h / max-h on the element itself (set via Tailwind) act as the floor/ceiling.
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value, ref])
}

function resetHeight(el: HTMLTextAreaElement | null) {
  // Clear the JS-set height so Tailwind's min-h takes over immediately.
  if (el) el.style.height = 'auto'
}

function useSmartScroll(
  containerRef: React.RefObject<HTMLDivElement | null>,
  bottomRef:    React.RefObject<HTMLDivElement | null>,
  streamTick:   unknown,
) {
  const atBottomRef  = useRef(true)
  const scrollingRef = useRef(false)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onScroll = () => {
      if (scrollingRef.current) return
      atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [containerRef])

  useEffect(() => {
    if (!atBottomRef.current) return
    scrollingRef.current = true
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    const t = setTimeout(() => { scrollingRef.current = false }, 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamTick])

  const forceBottom = useCallback(() => {
    atBottomRef.current  = true
    scrollingRef.current = true
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    setTimeout(() => { scrollingRef.current = false }, 300)
  }, [bottomRef])

  return { forceBottom }
}

// ─────────────────────────────────────────────────────────────────────────────
// SSE stream consumer (unchanged from Phase 2)
// ─────────────────────────────────────────────────────────────────────────────

async function consumeStream(
  message:     string,
  history:     { role: string; content: string }[],
  signal:      AbortSignal,
  onChunk:     (delta: string) => void,
  attachments?: FileAttachment[],
) {
  const body: Record<string, unknown> = { message, chat_history: history }
  if (attachments?.length) {
    body.attachments = attachments.map(a => ({
      base64:   a.base64,
      filename: a.name,
      mimeType: a.mediaType,
    }))
  }
  await ensureFreshToken()
  const res = await fetch('/api/chat/ariel/private', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body:    JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(await res.text().catch(() => res.statusText))

  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let   buf     = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (!payload || payload === '[DONE]') continue
      try {
        const parsed = JSON.parse(payload) as { chunk?: string; error?: string }
        if (parsed.error) throw new Error(parsed.error)
        if (parsed.chunk) onChunk(parsed.chunk)
      } catch (e) { if (e instanceof Error && e.message !== payload) throw e }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ArielChat — main component
// ─────────────────────────────────────────────────────────────────────────────

export function ArielChat({ onClose }: { onClose?: () => void } = {}) {
  const { data: onboardingData, clear: clearOnboarding } = useOnboarding()
  const { triggerProfileRefresh } = useChat()

  // ── Phase 1+2 state ────────────────────────────────────────────────────────
  const [messages,           setMessages]           = useState<ChatMessage[]>([])
  const [input,              setInput]              = useState('')
  const [streaming,          setStreaming]          = useState(false)
  const [showingTranslation, setShowingTranslation] = useState<Set<string>>(new Set())
  const [translatingIds,     setTranslatingIds]     = useState<Set<string>>(new Set())
  const [replyingTo,         setReplyingTo]         = useState<ChatMessage | null>(null)
  const [attachments,        setAttachments]        = useState<FileAttachment[]>([])
  const [attachError,        setAttachError]        = useState<string | null>(null)

  // ── Phase 3 state ──────────────────────────────────────────────────────────
  const [sessionId,     setSessionId]     = useState<string>(() => makeId())
  const [showHistory,   setShowHistory]   = useState(false)
  const [sessionList,   setSessionList]   = useState<SessionSummary[]>([])
  const [loadingList,   setLoadingList]   = useState(false)
  const [loadingSession, setLoadingSession] = useState(false)

  // ── Refs ───────────────────────────────────────────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textRef   = useRef<HTMLTextAreaElement>(null)
  const fileRef   = useRef<HTMLInputElement>(null)
  const abortRef  = useRef<AbortController | null>(null)
  const greetRef  = useRef(false)

  // Tracks whether streaming has ended and a sync is needed.
  // Using a ref (not state) so it never triggers a re-render.
  const needsSyncRef     = useRef(false)
  const sessionIdRef     = useRef(sessionId)
  sessionIdRef.current   = sessionId   // always current without stale closures

  const lastContent   = messages.at(-1)?.content ?? ''
  const inputDisabled = streaming || loadingSession
  useAutoHeight(textRef, input)
  const { forceBottom } = useSmartScroll(scrollRef, bottomRef, lastContent)

  // Re-focus the input once it actually becomes enabled again (DOM committed),
  // rather than calling textRef.current?.focus() synchronously right after
  // setStreaming(false) — that races the React re-render that removes the
  // `disabled` attribute, so the focus() call silently no-ops on a still-
  // disabled element and the user has to click back into the input.
  const wasDisabledRef = useRef(false)
  useEffect(() => {
    if (wasDisabledRef.current && !inputDisabled) {
      textRef.current?.focus()
    }
    wasDisabledRef.current = inputDisabled
  }, [inputDisabled])

  // ── Sync: fire once per exchange, after streaming ends ────────────────────
  // Detects the streaming true→false transition so we never sync mid-stream.
  useEffect(() => {
    if (streaming) {
      needsSyncRef.current = true
      return
    }
    if (!needsSyncRef.current || messages.length === 0) return
    needsSyncRef.current = false
    // messages is current here (effect runs after state settles)
    syncSession(sessionIdRef.current, messages)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming, messages])

  // ── Load session list on mount ─────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    setLoadingList(true)
    fetchSessionList().then(list => {
      if (!cancelled) setSessionList(list)
    }).finally(() => {
      if (!cancelled) setLoadingList(false)
    })
    return () => { cancelled = true }
  }, [])

  // ── Greeting ───────────────────────────────────────────────────────────────
  // Every variable is interpolated only when it actually has a value — an
  // empty careerStage or missing roles must never render as "****".
  useEffect(() => {
    if (greetRef.current || !onboardingData) return
    greetRef.current = true
    const first = onboardingData.fullName.split(' ')[0]

    // Prefer the live role/seniority preferences captured during onboarding.
    const roles = (onboardingData.roles ?? []).filter(r => r.role)
    let context = ''
    if (roles.length > 0) {
      const parts = roles.slice(0, 3).map(r => {
        const level = SENIORITY_LABELS[r.seniority] ?? ''
        return level ? `**${level} ${r.role}**` : `**${r.role}**`
      })
      const list = parts.length > 1
        ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
        : parts[0]
      context = ` I see you're targeting ${list} roles — great, that gives me a clear direction.`
    } else {
      const stage = onboardingData.careerStage
        ? (STAGE_LABELS[onboardingData.careerStage] ?? onboardingData.careerStage)
        : ''
      if (stage) context = ` I see you're at the **${stage}** stage.`
    }

    setMessages([{
      id:      makeId(),
      role:    'assistant',
      content: `Hi ${first}! Great to have you here.${context} Let's refine your Master Profile together — what would you like to tackle first?`,
    }])
    clearOnboarding()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── New conversation ───────────────────────────────────────────────────────
  const startNewSession = useCallback(() => {
    abortRef.current?.abort()
    setMessages([])
    setInput('')
    setReplyingTo(null)
    setAttachments([])
    setShowingTranslation(new Set())
    const newId = makeId()
    setSessionId(newId)
    sessionIdRef.current = newId
    needsSyncRef.current = false
    textRef.current?.focus()
  }, [])

  // ── Load a past session ────────────────────────────────────────────────────
  const loadSession = useCallback(async (id: string) => {
    if (id === sessionIdRef.current || streaming) return
    setLoadingSession(true)
    abortRef.current?.abort()
    try {
      const loaded = await fetchSessionMessages(id)
      if (!loaded) return
      setMessages(loaded)
      setSessionId(id)
      sessionIdRef.current = id
      setShowingTranslation(new Set())
      setReplyingTo(null)
      setAttachments([])
      needsSyncRef.current = false
      forceBottom()
    } finally {
      setLoadingSession(false)
    }
  }, [streaming, forceBottom])

  // ── Open history panel + refresh list ─────────────────────────────────────
  const openHistory = useCallback(() => {
    setShowHistory(true)
    setLoadingList(true)
    fetchSessionList().then(setSessionList).finally(() => setLoadingList(false))
  }, [])

  // ── File attachment handlers ───────────────────────────────────────────────
  const attachFiles = useCallback((incoming: File[]) => {
    if (!incoming.length) return

    // 0. Deduplicate — drop files already queued (matched by name + size)
    //    This prevents double-add when both onDrop and onChange fire, or when
    //    the user picks the same file twice.
    const deduped = incoming.filter(f =>
      !attachments.some(a => a.name === f.name && a.base64.length > 0
        // size check: base64 length ≈ ceil(size / 3) * 4, close enough for dedup
        // We compare name only here; the FileReader hasn't run yet so we can't
        // compare base64 — use name+type as a practical unique key instead.
      ) && !incoming.slice(0, incoming.indexOf(f)).some(
        earlier => earlier.name === f.name && earlier.size === f.size
      )
    )
    if (!deduped.length) return

    // 1. Admission control — walk the incoming files in order and accept each
    //    only if it fits within BOTH the count cap and the cumulative-size cap,
    //    seeded from what's already queued. A file over the per-file ceiling is
    //    always rejected. Rejections are surfaced via one inline notice, never
    //    a native alert().
    const perFileLimit = MAX_FILE_SIZE_MB  * 1024 * 1024
    const totalLimit   = MAX_TOTAL_SIZE_MB * 1024 * 1024

    let runningCount = attachments.length
    let runningBytes = attachments.reduce((sum, a) => sum + approxBytesFromBase64(a.base64), 0)

    const accepted: File[] = []
    let rejectedOversize = 0   // exceeds per-file ceiling
    let rejectedCapacity = 0   // would exceed count or cumulative-size ceiling

    for (const file of deduped) {
      if (file.size > perFileLimit) { rejectedOversize++; continue }
      if (runningCount + 1 > MAX_ATTACHMENTS)        { rejectedCapacity++; continue }
      if (runningBytes + file.size > totalLimit)     { rejectedCapacity++; continue }
      accepted.push(file)
      runningCount += 1
      runningBytes += file.size
    }

    // 2. Compose a single, concise notice for anything skipped
    if (rejectedOversize || rejectedCapacity) {
      const parts: string[] = []
      if (rejectedOversize) {
        parts.push(`${rejectedOversize} over ${MAX_FILE_SIZE_MB}MB each`)
      }
      if (rejectedCapacity) {
        parts.push(`limit is ${MAX_ATTACHMENTS} files / ${MAX_TOTAL_SIZE_MB}MB total`)
      }
      const skipped = rejectedOversize + rejectedCapacity
      setAttachError(`${skipped} file${skipped > 1 ? 's' : ''} skipped — ${parts.join(', ')}.`)
    }

    if (!accepted.length) return

    // 3. Read accepted files; state updates merge in as each reader resolves.
    //    The count guard is kept as a defensive backstop against interleaving.
    accepted.forEach(file => {
      const reader = new FileReader()
      reader.onload = ev => {
        const dataUrl = ev.target?.result as string
        setAttachments(cur => {
          if (cur.length >= MAX_ATTACHMENTS) return cur
          return [...cur, {
            base64:     dataUrl.split(',')[1] ?? '',
            mediaType:  file.type,
            previewUrl: dataUrl,
            name:       file.name,
          }]
        })
      }
      reader.readAsDataURL(file)
    })
  }, [attachments])

  // Auto-dismiss the attachment error notice after 4 s.
  useEffect(() => {
    if (!attachError) return
    const t = setTimeout(() => setAttachError(null), 4000)
    return () => clearTimeout(t)
  }, [attachError])

  const handleFileChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    attachFiles(files)
  }, [attachFiles])

  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files ?? [])
    if (!files.length) return
    e.preventDefault()
    attachFiles(files)
  }, [attachFiles])

  // ── Message action handlers ────────────────────────────────────────────────

  const deleteMessage = useCallback((id: string) => {
    setMessages(prev => prev.filter(m => m.id !== id))
    setReplyingTo(prev => prev?.id === id ? null : prev)
  }, [])

  const togglePin = useCallback((id: string) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, isPinned: !m.isPinned } : m))
  }, [])

  const handleTranslate = useCallback(async (id: string) => {
    const msg = messages.find(m => m.id === id)
    if (!msg) return
    if (msg.translatedContent) {
      setShowingTranslation(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
      return
    }
    setTranslatingIds(prev => new Set(prev).add(id))
    try {
      const translated = await mockTranslate(msg.content)
      setMessages(prev => prev.map(m => m.id === id ? { ...m, translatedContent: translated } : m))
      setShowingTranslation(prev => new Set(prev).add(id))
    } finally {
      setTranslatingIds(prev => { const n = new Set(prev); n.delete(id); return n })
    }
  }, [messages])

  const handleReply  = useCallback((msg: ChatMessage) => { setReplyingTo(msg); textRef.current?.focus() }, [])
  const handleReport = useCallback(async (id: string, content: string) => { await submitFeedback(id, content) }, [])

  // ── Edit user message: restore text to input, remove msg + everything after ─
  const handleEdit = useCallback((msgId: string) => {
    if (streaming) return
    const idx = messages.findIndex(m => m.id === msgId)
    if (idx === -1) return
    setInput(messages[idx].content)
    setMessages(prev => prev.slice(0, idx))
    setReplyingTo(null)
    textRef.current?.focus()
  }, [messages, streaming])

  // ── Regenerate: replace latest assistant reply with a fresh stream ─────────
  const handleRegenerate = useCallback(async (assistantMsgId: string) => {
    if (streaming) return

    const idx = messages.findIndex(m => m.id === assistantMsgId)
    if (idx === -1) return

    // Walk backwards to find the user turn that prompted this response
    let userIdx = idx - 1
    while (userIdx >= 0 && messages[userIdx].role !== 'user') userIdx--
    if (userIdx < 0) return

    const userMsg    = messages[userIdx]
    const history    = messages.slice(0, userIdx).map(m => ({ role: m.role, content: m.content }))
    const newAsstId  = makeId()

    // Replace old assistant bubble with a fresh empty one; keep everything before it
    setMessages(prev => [
      ...prev.slice(0, idx),
      { id: newAsstId, role: 'assistant', content: '' },
    ])
    forceBottom()
    setStreaming(true)

    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      await consumeStream(userMsg.content, history, ctrl.signal, chunk => {
        setMessages(prev => {
          const next = [...prev]
          const i    = next.findIndex(m => m.id === newAsstId)
          if (i !== -1) next[i] = { ...next[i], content: next[i].content + chunk }
          return next
        })
      })
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      const errMsg = err instanceof Error ? err.message : 'Something went wrong. Please try again.'
      setMessages(prev => {
        const next = [...prev]
        const i    = next.findIndex(m => m.id === newAsstId)
        if (i !== -1) next[i] = { ...next[i], content: errMsg }
        return next
      })
    } finally {
      // Refocus happens in the wasDisabledRef effect once the textarea's
      // `disabled` attribute actually clears in the DOM (see above).
      setStreaming(false)
      triggerProfileRefresh()
    }
  }, [messages, streaming, forceBottom, triggerProfileRefresh])

  // ── Send ───────────────────────────────────────────────────────────────────
  const sendMessage = useCallback(async (override?: string) => {
    const rawText = (override ?? input).trim() || (attachments.length ? 'Please look at the attached files.' : '')
    if (!rawText || streaming) return

    const replySnippet  = replyingTo
      ? replyingTo.content.slice(0, REPLY_SNIPPET_LEN) + (replyingTo.content.length > REPLY_SNIPPET_LEN ? '…' : '')
      : null
    const fullText = replySnippet ? `Replying to: "${replySnippet}"\n\n${rawText}` : rawText

    setInput('')
    resetHeight(textRef.current)
    setReplyingTo(null)
    const capturedAttachments = attachments
    setAttachments([])

    const history     = messages.map(m => ({ role: m.role, content: m.content }))
    const assistantId = makeId()

    // Store the first image for in-chat preview (ChatMessage.image is display-only)
    const previewImage = capturedAttachments.find(a => a.mediaType.startsWith('image/'))

    setMessages(prev => [
      ...prev,
      { id: makeId(), role: 'user', content: rawText, replyContext: replySnippet ?? undefined, image: previewImage, attachments: capturedAttachments.length ? capturedAttachments : undefined },
      { id: assistantId, role: 'assistant', content: '' },
    ])
    forceBottom()
    setStreaming(true)

    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      await consumeStream(fullText, history, ctrl.signal, chunk => {
        setMessages(prev => {
          const next = [...prev]
          const idx  = next.findIndex(m => m.id === assistantId)
          if (idx !== -1) next[idx] = { ...next[idx], content: next[idx].content + chunk }
          return next
        })
      }, capturedAttachments.length ? capturedAttachments : undefined)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      const msg = err instanceof Error ? err.message : 'Something went wrong. Please try again.'
      setMessages(prev => {
        const next = [...prev]
        const idx  = next.findIndex(m => m.id === assistantId)
        if (idx !== -1) next[idx] = { ...next[idx], content: msg }
        return next
      })
    } finally {
      // Refocus happens in the wasDisabledRef effect once the textarea's
      // `disabled` attribute actually clears in the DOM (see above).
      setStreaming(false)

      // Signal that the Master Profile may have changed so any mounted
      // Confidence Score display can re-fetch (see ChatContext.profileVersion).
      // Tool-call profile edits (update_experience/update_skills/etc.) commit
      // synchronously on the server before this response finishes streaming,
      // so the immediate trigger already covers those. CV-attachment
      // ingestion instead runs as a fire-and-forget background task that
      // completes *after* the response returns, so also schedule a delayed
      // second trigger to catch it.
      triggerProfileRefresh()
      if (capturedAttachments.length) {
        setTimeout(triggerProfileRefresh, 5000)
      }
    }
  }, [input, messages, streaming, replyingTo, attachments, forceBottom, triggerProfileRefresh])

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
    if (e.key === 'Escape') setReplyingTo(null)
  }

  // ── Input bar JSX (inlined at each call site — NOT a nested component) ──────
  // Defining a component function inside another component causes React to treat
  // it as a new type on every render, unmounting the DOM node (and losing focus)
  // on every keystroke. We use a plain function that returns JSX and call it
  // directly so the returned elements become part of the parent's render tree.
  const renderInputBar = (placeholder: string) => (
    <div
      className="flex-shrink-0 border-t border-slate-100 bg-white px-3 pt-2 pb-2 space-y-1.5"
      onDragOver={e => e.preventDefault()}
      onDrop={e => { e.preventDefault(); attachFiles(Array.from(e.dataTransfer.files)) }}
    >
      {/* Hidden file input — always in the DOM so fileRef is always valid */}
      <input
        ref={fileRef}
        type="file"
        accept="image/*,video/*,.pdf,.doc,.docx"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Reply context banner */}
      {replyingTo && (
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-teal-50 border border-teal-200 text-[11.5px]">
          <ReplyIcon />
          <span className="text-teal-700 font-medium shrink-0">Replying to:</span>
          <span className="text-slate-500 flex-1 truncate">{replyingTo.content.slice(0, REPLY_SNIPPET_LEN)}</span>
          <button onClick={() => setReplyingTo(null)} className="ml-auto text-slate-400 hover:text-slate-700 focus-visible:text-slate-700 transition text-[15px] leading-none" title="Cancel reply" aria-label="Cancel reply">×</button>
        </div>
      )}

      {/* Attachment pills */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 p-1 overflow-y-auto max-h-24">
          {attachments.map((a, i) => {
            const truncateName = (name: string) => {
              const dot  = name.lastIndexOf('.')
              const base = dot > 0 ? name.slice(0, dot) : name
              const ext  = dot > 0 ? name.slice(dot)   : ''
              if (base.length <= 10) return name
              return `${base.slice(0, 8)}…${ext}`
            }

            const openPreview = () => {
              // Build a blob URL from the stored base64 so the file opens in a new tab.
              // For images the previewUrl data-URI works directly; for other types we
              // must construct a proper blob so the browser picks the right viewer.
              if (a.previewUrl && a.mediaType.startsWith('image/')) {
                window.open(a.previewUrl, '_blank', 'noopener')
                return
              }
              try {
                const binary = atob(a.base64)
                const bytes  = new Uint8Array(binary.length)
                for (let b = 0; b < binary.length; b++) bytes[b] = binary.charCodeAt(b)
                const blob = new Blob([bytes], { type: a.mediaType })
                const url  = URL.createObjectURL(blob)
                const win  = window.open(url, '_blank', 'noopener')
                // Revoke after the tab has had time to load the blob
                win?.addEventListener('load', () => URL.revokeObjectURL(url), { once: true })
                // Fallback revoke after 60 s in case load never fires
                setTimeout(() => URL.revokeObjectURL(url), 60_000)
              } catch {
                // If atob fails (e.g. empty base64 during async read), no-op
              }
            }

            return (
              <div
                key={i}
                className="flex items-center gap-1.5 text-xs px-2 py-1 rounded text-white"
                style={{ background: TOKENS.color.primary }}
              >
                {/* Clickable body — opens file preview */}
                <button
                  type="button"
                  onClick={openPreview}
                  className="flex items-center gap-1.5 cursor-pointer rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
                  title={`Preview: ${a.name}`}
                  aria-label={`Preview attachment ${a.name}`}
                >
                  {a.mediaType.startsWith('image/') ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.previewUrl} alt="" className="w-4 h-4 rounded object-cover shrink-0 opacity-90" />
                  ) : (
                    <span className="shrink-0 font-bold uppercase opacity-80">
                      {a.name.split('.').pop()?.slice(0, 3) ?? '📎'}
                    </span>
                  )}
                  <span className="max-w-[90px] leading-none">{truncateName(a.name)}</span>
                </button>

                {/* Remove — stops propagation so focus doesn't linger on the button */}
                <button
                  type="button"
                  onClick={e => {
                    e.stopPropagation()
                    setAttachments(prev => prev.filter((_, idx) => idx !== i))
                    textRef.current?.focus()
                  }}
                  className="shrink-0 opacity-70 hover:opacity-100 transition leading-none ml-0.5"
                  title="Remove"
                  aria-label={`Remove ${a.name}`}
                >✕</button>
              </div>
            )
          })}
        </div>
      )}

      {/* Attachment error notice — auto-dismisses after 4 s */}
      {attachError && (
        <div
          role="alert"
          aria-live="polite"
          className="flex items-center gap-1.5 px-1 text-[11px] text-red-600"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{attachError}</span>
        </div>
      )}

      {/* Textarea row */}
      <div className="flex items-end gap-1.5">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          title={`Attach files (images, PDFs, videos, Word docs) — max ${MAX_ATTACHMENTS} files, up to ${MAX_TOTAL_SIZE_MB}MB total${
            attachments.length > 0 ? ` (${attachments.length}/${MAX_ATTACHMENTS} attached)` : ''
          }`}
          aria-label="Attach files"
          disabled={streaming || attachments.length >= MAX_ATTACHMENTS}
          className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition disabled:opacity-40"
        >
          <PaperclipIcon />
        </button>

        <textarea
          ref={textRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={placeholder}
          dir="auto"
          rows={1}
          autoFocus
          disabled={inputDisabled}
          className="flex-1 resize-none overflow-y-auto rounded-xl border border-slate-200 px-3 py-2.5 text-[13px] leading-[1.4] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-teal-400 focus:ring-2 focus:ring-teal-500/20 transition disabled:opacity-50 bg-white min-h-[44px] max-h-[112px] [unicode-bidi:plaintext] text-start"
        />

        {streaming ? (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            title="Stop generation"
            aria-label="Stop generation"
            className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-white transition active:scale-95 bg-rose-500 hover:bg-rose-600"
          >
            <StopIcon s={15} />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => sendMessage()}
            disabled={(!input.trim() && !attachments.length) || loadingSession}
            title="Send (Enter)"
            aria-label="Send message"
            className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-white transition active:scale-95 disabled:opacity-35 disabled:pointer-events-none"
            style={{ background: TOKENS.color.primary }}
          >
            <SendIcon s={15} />
          </button>
        )}
      </div>

    </div>
  )

  // ── Welcome screen ─────────────────────────────────────────────────────────
  if (messages.length === 0 && !loadingSession) {
    const latestSession = sessionList[0] ?? null   // list is already newest-first

    const actions: { icon: string; label: string; prompt: string }[] = [
      {
        icon:   '🗺️',
        label:  'Map my career gaps',
        prompt: "I want to map the gaps between my current experience and my target role. Let's start.",
      },
      {
        icon:   '🎤',
        label:  'Prepare for an interview',
        prompt: 'I have an interview coming up. Help me prepare.',
      },
      {
        icon:   '🔍',
        label:  'Analyze a job description',
        prompt: "I'd like to analyze a job description together. I'll paste it now.",
      },
      {
        icon:   '🛤️',
        label:  'Build my career roadmap',
        prompt: 'Help me build a realistic roadmap to my next career milestone.',
      },
    ]

    return (
      <div className="flex flex-col h-full">
        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">

          {/* Identity block */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white text-base font-bold shrink-0"
              style={{ background: TOKENS.color.primary }}>A</div>
            <div>
              <p className="text-[14px] font-bold text-slate-900 leading-tight">Ariel</p>
              <p className="text-[11.5px] text-slate-400 leading-tight">Career Intelligence Agent</p>
            </div>
          </div>

          {/* Resume-recent session shortcut — shown only when history exists */}
          {latestSession && (
            <button
              onClick={() => loadSession(latestSession.session_id)}
              className="w-full flex items-center gap-3 px-3.5 py-3 rounded-xl border border-teal-200 bg-teal-50 hover:bg-teal-100 transition text-left"
            >
              <span className="text-[18px] leading-none shrink-0">💬</span>
              <div className="min-w-0">
                <p className="text-[12px] font-semibold text-teal-700 leading-tight">Continue recent conversation</p>
                <p dir="auto" className="text-[11px] text-teal-500 truncate mt-0.5">
                  {latestSession.preview || 'Pick up where you left off'}
                </p>
              </div>
              <svg className="ml-auto shrink-0 text-teal-400" width={14} height={14} viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          )}

          {/* Divider label */}
          <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-wider px-0.5">
            {latestSession ? 'Or start something new' : 'What would you like to work on?'}
          </p>

          {/* Compact suggestion pills — icon + title only, wrap to fill width.
              Kept visually secondary to the auto-focused input below. */}
          <div className="flex flex-wrap gap-1.5">
            {actions.map(a => (
              <button
                key={a.label}
                onClick={() => sendMessage(a.prompt)}
                disabled={streaming}
                className="inline-flex items-center gap-1.5 pl-2 pr-2.5 py-1.5 rounded-full border border-slate-200 bg-white text-[12px] font-medium text-slate-700 hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700 transition disabled:opacity-50"
              >
                <span className="text-[14px] leading-none shrink-0">{a.icon}</span>
                {a.label}
              </button>
            ))}
          </div>

        </div>

        {renderInputBar("Or just type to start…")}
      </div>
    )
  }

  // ── Active chat ─────────────────────────────────────────────────────────────
  // Id of the last assistant message — used for Regenerate visibility
  const lastAsstId = [...messages].reverse().find(m => m.role === 'assistant')?.id
  const lastMsgId  = messages.at(-1)?.id

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100 bg-white flex-shrink-0 z-10">
        {/* Left: avatar + name */}
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-full text-white text-[11px] font-bold flex items-center justify-center shrink-0"
            style={{ background: TOKENS.color.primary }}>A</div>
          <p className="text-[13px] font-semibold text-slate-700 truncate">Ariel</p>
        </div>
        {/* Right: icon buttons — all the same 28px square size for alignment */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={openHistory}
            title="Conversation history"
            className={`h-7 w-7 flex items-center justify-center rounded-lg transition
              ${showHistory ? 'text-teal-600 bg-teal-50' : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'}`}
          >
            <HistoryIcon s={14} />
          </button>
          <button
            onClick={startNewSession}
            title="New conversation"
            className="h-7 w-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition text-[15px] leading-none"
          >↺</button>
          {onClose && (
            <>
              {/* Minimize — hides the panel; the conversation stays intact and
                  can be reopened from the floating "Ask Ariel" launcher.
                  Also a natural moment to re-check the Confidence Score in
                  case a background CV-ingestion task finished since the last
                  per-message trigger. */}
              <button
                onClick={() => { triggerProfileRefresh(); onClose() }}
                title="Minimize"
                aria-label="Minimize Ariel"
                className="h-7 w-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
              >
                <svg width={13} height={13} viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <line x1="5" y1="19" x2="19" y2="19" />
                </svg>
              </button>
              {/* Close — also hides the panel (state preserved); reopen anytime
                  via the launcher. */}
              <button
                onClick={() => { triggerProfileRefresh(); onClose() }}
                title="Close"
                aria-label="Close Ariel"
                className="h-7 w-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
              >
                <svg width={13} height={13} viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Body — relative container so the history panel can overlay it */}
      <div className="relative flex-1 min-h-0">
        {/* Message list */}
        <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-4 space-y-5">
          {loadingSession ? (
            <div className="flex items-center justify-center h-32 text-slate-400">
              <SpinnerIcon s={22} />
            </div>
          ) : (
            messages.map(msg => {
              // Suppress the empty placeholder bubble during TTFB — the
              // TypingIndicator below already signals Ariel is working.
              if (streaming && msg.id === lastMsgId && msg.role === 'assistant' && msg.content === '') return null
              return <MessageBubble
                key={msg.id}
                message={msg}
                isStreaming={streaming && msg.id === lastMsgId && msg.role === 'assistant'}
                showTranslation={showingTranslation.has(msg.id)}
                isTranslating={translatingIds.has(msg.id)}
                isLatestAssistant={!streaming && msg.role === 'assistant' && msg.id === lastAsstId}
                onDelete={deleteMessage}
                onReply={handleReply}
                onPin={togglePin}
                onTranslate={handleTranslate}
                onReport={handleReport}
                onEdit={handleEdit}
                onRegenerate={handleRegenerate}
              />
            })
          )}
          {streaming && messages.at(-1)?.role === 'assistant' && messages.at(-1)?.content === '' && (
            <TypingIndicator />
          )}
          <div ref={bottomRef} />
        </div>

        {/* History slide-in panel — overlays only the message list */}
        <HistoryPanel
          isOpen={showHistory}
          onClose={() => setShowHistory(false)}
          sessions={sessionList}
          loadingList={loadingList}
          activeSessionId={sessionId}
          onSelectSession={loadSession}
          onNewSession={startNewSession}
        />
      </div>

      {renderInputBar("Type your reply… (Shift+Enter for new line)")}
    </div>
  )
}

```

## `web_dashboard/src/components/ChatLauncher.tsx`

_Ariel interaction button (FAB launcher)_

```tsx
'use client'

import { usePathname } from 'next/navigation'
import { useChat } from '@/contexts/ChatContext'
import { useAuth } from '@/contexts/AuthContext'
import { TOKENS }  from '@/lib/tokens'

const ONBOARDING_ROUTES = ['/onboarding', '/profile-builder']

// Strict check against BOTH the React pathname and the live browser URL —
// during soft-routing transitions they can disagree for a frame, which let
// the launcher flash mid-onboarding. Hidden if either says onboarding.
function isOnOnboardingRoute(reactPathname: string | null): boolean {
  const browserPathname = typeof window !== 'undefined' ? window.location.pathname : ''
  return ONBOARDING_ROUTES.some(r =>
    (reactPathname ?? '').startsWith(r) || browserPathname.startsWith(r)
  )
}

function ChatIcon() {
  return (
    <svg width={18} height={18} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

// Floating launcher for Ariel (authenticated career agent).
// Hidden when the panel is already open, or when the user is not signed in.
export function ChatLauncher() {
  const { isOpen, isEliyaOpen, jobContext, openChat } = useChat()
  const { user } = useAuth()
  const pathname = usePathname()

  // Ariel only exists for completed profiles, and never during onboarding.
  const profileCompleted =
    (user?.user_metadata as Record<string, unknown> | undefined)?.profile_completed === true
  const onOnboardingRoute = isOnOnboardingRoute(pathname)

  // Only show for authenticated, onboarded users; hide if any chat panel is open
  if (!user || !profileCompleted || onOnboardingRoute || isOpen || isEliyaOpen) return null

  const hasContext = Boolean(jobContext)

  return (
    <button
      onClick={() => openChat()}
      title="Open Ariel — your career agent"
      aria-label="Open Ariel career agent"
      className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 h-12 px-4 rounded-full text-white transition-all duration-200 active:scale-95 hover:opacity-90"
      style={{
        background: TOKENS.color.primary,
        boxShadow:  '0 4px 20px rgba(13,148,136,0.40)',
      }}
    >
      {/* Context dot — visible when a job topic is loaded */}
      {hasContext && (
        <span
          className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full border-2 border-white"
          style={{ background: '#f59e0b' }}
          title="Job context loaded"
        />
      )}
      <span className="flex-shrink-0"><ChatIcon /></span>
      <span className="text-[13px] font-semibold tracking-tight">Ask Ariel</span>
    </button>
  )
}

```

## `web_dashboard/tailwind.config.ts`

_Tailwind design tokens_

```ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      colors: {
        ja: {
          // ── Canvas & surface ──────────────────────────────────────────────
          bg:         '#F8FAFC',   // slate-50  — cool page canvas
          surface:    '#FFFFFF',   // pure white card / panel
          surfaceHover: '#F8FAFC', // subtle hover state for interactive surfaces

          // ── Text ─────────────────────────────────────────────────────────
          ink:        '#0F172A',   // slate-900 — primary text
          ink2:       '#334155',   // slate-700 — secondary text
          muted:      '#64748B',   // slate-500 — labels, captions
          subtle:     '#94A3B8',   // slate-400 — placeholders, disabled

          // ── Borders & dividers ────────────────────────────────────────────
          line:       '#E2E8F0',   // slate-200 — standard dividers / card borders
          lineSoft:   '#F1F5F9',   // slate-100 — ultra-subtle inner separators

          // ── Brand ─────────────────────────────────────────────────────────
          primary:       '#0D9488',   // teal-600 — serene, modern, non-corporate
          primaryHover:  '#0F766E',   // teal-700 — ~5% darker on hover
          primarySubtle: '#F0FDFA',   // teal-50  — selected states, pill bg

          // ── Semantic feedback (mirrors --ja-* vars in globals.css) ────────
          success:       '#059669',   // emerald-600
          successSubtle: '#ECFDF5',   // emerald-50
          warn:          '#D97706',   // amber-600
          warnSubtle:    '#FFFBEB',   // amber-50
          danger:        '#DC2626',   // red-600
          dangerSubtle:  '#FEF2F2',   // red-50

          // ── Fixed brand constants ─────────────────────────────────────────
          linkedin:      '#0A66C2',   // LinkedIn brand blue — external constant
          inkDeep:       '#0A1F1C',   // near-black teal — dark hero/auth gradient stop
        },
      },
      maxWidth: {
        content: '1120px',
      },
      boxShadow: {
        // ── Elevation system (layered, Intercom-grade) ─────────────────────
        //    Each tier stacks a diffuse ambient layer with a tighter key layer.
        //    Keep all alpha values low so cards look lifted, not heavy.
        'elevation-1': [
          '0 1px 2px rgba(0,0,0,0.04)',
          '0 1px 4px rgba(0,0,0,0.06)',
        ].join(', '),
        'elevation-2': [
          '0 2px 4px rgba(0,0,0,0.04)',
          '0 4px 12px rgba(0,0,0,0.08)',
        ].join(', '),
        'floating': [
          '0 4px 6px rgba(0,0,0,0.04)',
          '0 12px 32px rgba(0,0,0,0.12)',
          '0 1px 0px rgba(255,255,255,0.8) inset',
        ].join(', '),
        // legacy alias — preserves existing uses of shadow-card
        'card': '0 1px 2px rgba(0,0,0,0.04), 0 1px 4px rgba(0,0,0,0.06)',
      },
      borderRadius: {
        // explicit semantic radius tokens
        'sm':  '6px',
        'md':  '8px',
        'lg':  '12px',
        'xl':  '16px',
        '2xl': '20px',
      },
    },
  },
  plugins: [],
}

export default config

```

## `web_dashboard/src/app/globals.css`

_Global CSS / design token variables_

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ── Design tokens ─────────────────────────────────────────────────────────────
   Single source of truth for the Intercom-inspired premium design system.
   All component-level inline styles should reference these vars.
   ─────────────────────────────────────────────────────────────────────────── */
:root {
  /* Brand */
  --ja-primary:        #0D9488;   /* teal-600 — serene, modern, non-corporate  */
  --ja-primary-hover:  #0F766E;   /* teal-700 — ~5% darker on interactive hover*/
  --ja-primary-subtle: #F0FDFA;   /* teal-50  — selected states, pill bg       */

  /* Semantic feedback */
  --ja-success:       #059669;   /* emerald-600                                */
  --ja-success-subtle:#ECFDF5;   /* emerald-50                                 */
  --ja-warn:          #D97706;   /* amber-600                                  */
  --ja-warn-subtle:   #FFFBEB;   /* amber-50                                   */
  --ja-danger:        #DC2626;   /* red-600                                    */
  --ja-danger-subtle: #FEF2F2;   /* red-50                                     */

  /* Canvas & surfaces */
  --ja-bg:            #F8FAFC;   /* slate-50 — page background                 */
  --ja-surface:       #FFFFFF;   /* card / panel face                          */
  --ja-surface-hover: #F8FAFC;   /* interactive surface hover                  */

  /* Text */
  --ja-ink:           #0F172A;   /* slate-900 — primary body copy              */
  --ja-ink2:          #334155;   /* slate-700 — secondary labels               */
  --ja-muted:         #64748B;   /* slate-500 — captions, placeholders         */
  --ja-subtle:        #94A3B8;   /* slate-400 — disabled, ghost text           */

  /* Borders */
  --ja-line:          #E2E8F0;   /* slate-200 — card borders, dividers         */
  --ja-line-soft:     #F1F5F9;   /* slate-100 — inner separators               */

  /* Fixed brand constants */
  --ja-linkedin:      #0A66C2;   /* LinkedIn brand blue — external constant    */
  --ja-ink-deep:      #0A1F1C;   /* near-black teal — dark hero gradient stop  */

  /* Elevation (mirrors tailwind.config.ts boxShadow tokens) */
  --ja-elevation-1:   0 1px 2px rgba(0,0,0,0.04), 0 1px 4px rgba(0,0,0,0.06);
  --ja-elevation-2:   0 2px 4px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.08);
  --ja-floating:      0 4px 6px rgba(0,0,0,0.04), 0 12px 32px rgba(0,0,0,0.12),
                      0 1px 0px rgba(255,255,255,0.8) inset;

  /* Radius */
  --ja-radius-sm:     6px;
  --ja-radius-md:     8px;
  --ja-radius-lg:     12px;
  --ja-radius-xl:     16px;
}

/* ── Base ──────────────────────────────────────────────────────────────────── */

html,
body {
  background: var(--ja-bg);
}

body {
  font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-feature-settings: 'cv11', 'ss01';
  color: var(--ja-ink);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* ── Accessibility ─────────────────────────────────────────────────────────── */

button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--ja-primary);
  outline-offset: 2px;
  border-radius: var(--ja-radius-sm);
}

input[type='range'] {
  accent-color: var(--ja-primary);
}

/* ── Animations ────────────────────────────────────────────────────────────── */

@keyframes ja-ping {
  75%, 100% {
    transform: scale(2.2);
    opacity: 0;
  }
}

@keyframes ja-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0);   }
}

@keyframes ja-fade-in-up {
  from { opacity: 0; transform: translateY(28px); }
  to   { opacity: 1; transform: translateY(0);    }
}

.ja-animate-section {
  opacity: 0;
  animation: ja-fade-in-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

.ja-animate-section.ja-visible {
  opacity: 1;
}

/* ── Scrollbars ────────────────────────────────────────────────────────────── */

*::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

*::-webkit-scrollbar-track {
  background: transparent;
}

*::-webkit-scrollbar-thumb {
  background: var(--ja-line);
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: content-box;
}

*::-webkit-scrollbar-thumb:hover {
  background: var(--ja-muted);
  background-clip: content-box;
}

```
