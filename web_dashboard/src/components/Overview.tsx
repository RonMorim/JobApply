'use client'
import { useCallback, useEffect, useState } from 'react'
import { getGreetingName } from '@/lib/nameUtils'
import { TOKENS } from '@/lib/tokens'
import type { ApiFeedJob } from '@/lib/apiTypes'
import { Skeleton } from './ui/Skeleton'
import { SparkIcon, UserBadgeIcon, FileIcon, SlidersIcon, ArrowIcon } from './icons'
import { TrustDashboard } from './TrustDashboard'
import { fetchScraperStatus, type ScraperStatus } from '@/lib/api'

// ── LinkedIn Scraper Status Banners ──────────────────────────────────────────
//
// BLOCKED — enrichment loop auto-paused after ≥ 2 redirect-loop errors
//           (ERR_TOO_MANY_REDIRECTS = LinkedIn bot-detection signal).
// PAUSED  — manually paused via reset_linkedin_scraper.py --pause while a
//            fresh li_at cookie is being configured.  Not an error state.

function LinkedInBlockedBanner({ blockedAt }: { blockedAt: string | null }) {
  const formattedAt = blockedAt
    ? new Date(blockedAt).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
    : null

  return (
    <div
      className="rounded-xl px-4 py-3.5 flex items-start gap-3"
      style={{ background: 'oklch(0.97 0.04 25)', border: '1px solid oklch(0.88 0.08 25)' }}
      role="alert"
    >
      <span className="text-[18px] shrink-0 mt-0.5" aria-hidden="true">🚫</span>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-bold text-slate-800 mb-0.5">
          LinkedIn Connection Blocked
        </p>
        <p className="text-[12px] text-slate-600 leading-relaxed">
          The scraper hit a redirect loop (bot-detection) and has been paused to protect your
          IP.{formattedAt && <> Blocked at {formattedAt}.</>}
          {' '}Run{' '}
          <code className="font-mono text-[11px]">venv/bin/python -m backend.scripts.reset_linkedin_scraper --pause</code>
          , update <code className="font-mono text-[11px]">LINKEDIN_LI_AT</code> in{' '}
          <code className="font-mono text-[11px]">backend/.env</code>, then run{' '}
          <code className="font-mono text-[11px]">--resume</code>.
        </p>
      </div>
    </div>
  )
}

function LinkedInPausedBanner() {
  return (
    <div
      className="rounded-xl px-4 py-3.5 flex items-start gap-3"
      style={{ background: 'oklch(0.97 0.04 55)', border: '1px solid oklch(0.90 0.06 55)' }}
      role="status"
    >
      <span className="text-[18px] shrink-0 mt-0.5" aria-hidden="true">⏸</span>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-bold text-slate-800 mb-0.5">
          LinkedIn Scraper — Maintenance Pause
        </p>
        <p className="text-[12px] text-slate-600 leading-relaxed">
          The enrichment loop is paused while a fresh cookie is being configured.
          Update <code className="font-mono text-[11px]">LINKEDIN_LI_AT</code> in{' '}
          <code className="font-mono text-[11px]">backend/.env</code>, then run{' '}
          <code className="font-mono text-[11px]">venv/bin/python -m backend.scripts.reset_linkedin_scraper --resume</code>{' '}
          to restart scraping.
        </p>
      </div>
    </div>
  )
}

// ── KPI strip ─────────────────────────────────────────────────────────────────
// Pure typography — no boxes, no borders. Three stats in a horizontal rule.

function KPIStat({ label, value, sub, accent }: {
  label: string; value: string | number; sub: string; accent: string
}) {
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <span
        className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-400"
      >
        {label}
      </span>
      <span
        className="text-[38px] font-semibold tabular-nums leading-none tracking-tight text-slate-900"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </span>
      <span className="text-[12px] text-slate-400 leading-snug">{sub}</span>
      {/* Per-stat accent underline — replaces the card border as the only decoration */}
      <span className="block h-[3px] w-8 rounded-full mt-1" style={{ background: accent }} />
    </div>
  )
}

function KPIRow({ jobsScannedToday, highMatches, actionsTaken, loading }: {
  jobsScannedToday: number
  highMatches:      number
  actionsTaken:     number
  loading:          boolean
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-3 gap-8">
        {[0, 1, 2].map(i => (
          <div key={i} className="flex flex-col gap-2">
            <Skeleton className="h-2.5 w-24" />
            <Skeleton className="h-9 w-16" />
            <Skeleton className="h-2.5 w-32" />
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="grid grid-cols-3 gap-8">
      <KPIStat
        label="Jobs scanned today"
        value={jobsScannedToday}
        sub="New roles discovered by agents"
        accent={TOKENS.color.primary}
      />
      <KPIStat
        label="High matches"
        value={highMatches}
        sub="ATS score above 85"
        accent={TOKENS.color.success}
      />
      <KPIStat
        label="Actions taken"
        value={actionsTaken}
        sub="Analyses run or CVs tailored"
        accent={TOKENS.color.violet}
      />
    </div>
  )
}


// ── Quick actions ─────────────────────────────────────────────────────────────
// Plain bordered list — no card backgrounds, no shadows.

function QuickActions({ newCount, savedCount, onGo }: {
  newCount: number; savedCount: number; onGo: (tab: string) => void
}) {
  const items = [
    {
      id: 'review', tab: 'feed',
      label: `Review your ${newCount} new matches`,
      sub: 'Top matches this morning',
      accent: TOKENS.color.primary,
      Icon: SparkIcon,
    },
    {
      id: 'profile', tab: 'profile-builder:optimize_gaps',
      label: 'Review your profile strengths',
      sub: 'Targets low-confidence claims first',
      accent: TOKENS.color.violet,
      Icon: UserBadgeIcon,
    },
    {
      id: 'cv', tab: 'profile-builder',
      label: 'Update your CV',
      sub: 'Open the AI Profile Builder',
      accent: TOKENS.color.success,
      Icon: FileIcon,
    },
    {
      id: 'prefs', tab: 'prefs',
      label: 'Tune your preferences',
      sub: 'Match score, work mode, location',
      accent: TOKENS.color.warn,
      Icon: SlidersIcon,
    },
  ]

  return (
    <div>
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-[13px] font-semibold uppercase tracking-[0.12em] text-slate-400">
          Quick actions
        </h2>
      </div>
      {/* Divided list — no individual card borders */}
      <div className="divide-y divide-slate-100">
        {items.map(it => {
          const { Icon } = it
          return (
            <button
              key={it.id}
              onClick={() => onGo(it.tab)}
              className="group w-full text-left flex items-center gap-4 py-3.5 hover:bg-slate-50/60 transition-colors duration-150 rounded-lg px-1 -mx-1"
            >
              <span
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg shrink-0"
                style={{
                  background: `color-mix(in oklab, ${it.accent} 10%, white)`,
                  color: it.accent,
                }}
              >
                <Icon s={14} />
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-[13.5px] font-medium text-slate-800 leading-snug">
                  {it.label}
                </span>
                <span className="block text-[12px] text-slate-400 mt-0.5">{it.sub}</span>
              </span>
              <span className="text-slate-300 group-hover:text-slate-500 transition-colors shrink-0">
                <ArrowIcon s={13} />
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Top match row ─────────────────────────────────────────────────────────────
// A lightweight read-only row — NOT a full JobCard accordion.
// Clicking navigates the user to the Matches tab rather than expanding in-place.

function ScorePip({ score }: { score: number }) {
  const color =
    score >= 80 ? TOKENS.color.success :
    score >= 60 ? TOKENS.color.primary :
    score >= 40 ? TOKENS.color.warn    :
                  TOKENS.color.danger

  return (
    <div className="flex flex-col items-center gap-0.5 shrink-0 w-10">
      <span
        className="text-[15px] font-bold tabular-nums leading-none"
        style={{ color }}
      >
        {score.toFixed(1)}
      </span>
      <span className="text-[9px] font-semibold uppercase tracking-wide text-slate-400">
        ATS
      </span>
    </div>
  )
}

function TopMatchRow({ job, onClick }: { job: ApiFeedJob; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group w-full text-left flex items-center gap-4 py-3.5 border-b border-slate-100 last:border-none hover:bg-slate-50/50 transition-colors duration-150 rounded-lg px-1 -mx-1"
    >
      <ScorePip score={job.match_score} />

      <div className="flex-1 min-w-0">
        <p className="text-[13.5px] font-semibold text-slate-900 truncate leading-snug">
          {job.title}
        </p>
        <p className="text-[12px] text-slate-500 truncate mt-0.5">
          {job.company}
          {job.location && (
            <span className="text-slate-300 mx-1.5">·</span>
          )}
          {job.location}
        </p>
        {/* Reason tags as inline text — no pill borders */}
        {job.reasons.length > 0 && (
          <p className="text-[11px] text-slate-400 mt-1 truncate">
            {job.reasons.slice(0, 2).map(r => r.label).join(' · ')}
          </p>
        )}
      </div>

      <span className="text-slate-300 group-hover:text-slate-500 transition-colors shrink-0">
        <ArrowIcon s={13} />
      </span>
    </button>
  )
}

// ── Skeleton row ──────────────────────────────────────────────────────────────

function TopMatchSkeleton({ opacity }: { opacity: number }) {
  return (
    <div
      className="flex items-center gap-4 py-3.5 border-b border-slate-100 last:border-none"
      style={{ opacity }}
    >
      <div className="flex flex-col items-center gap-1 w-10 shrink-0">
        <Skeleton className="h-4 w-8" />
        <Skeleton className="h-2 w-6" />
      </div>
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-3.5 w-48" />
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-2.5 w-40" />
      </div>
    </div>
  )
}

// ── Greeting helpers ───────────────────────────────────────────────────────────

function _timeGreeting(): string {
  const h = new Date().getHours()
  if (h >= 5  && h < 12) return 'Good morning'
  if (h >= 12 && h < 17) return 'Good afternoon'
  if (h >= 17 && h < 21) return 'Good evening'
  return 'Good night'
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface OverviewProps {
  userId:           string
  jobsScannedToday: number
  feedJobs:         ApiFeedJob[]
  jobsLoading:      boolean
  savedIds:         string[]
  displayName?:     string
  onSave:     (id: string) => void
  onReviewCV: (id: string) => void
  onGo:       (tab: string, jobId?: string) => void
}

// ── Overview ──────────────────────────────────────────────────────────────────

export function Overview({
  userId, jobsScannedToday, feedJobs, jobsLoading, savedIds, displayName,
  onSave, onReviewCV, onGo,
}: OverviewProps) {
  const highMatches  = feedJobs.filter(j => j.match_score > 85.0).length
  const actionsTaken = feedJobs.filter(j => j.why_ron || j.has_tailored_cv).length
  const previewJobs  = feedJobs.slice(0, 4)

  const handleMatchClick    = useCallback(()              => onGo('feed'),         [onGo])
  const handleMatchJobClick = useCallback((jobId: string) => onGo('feed', jobId),  [onGo])

  // ── LinkedIn scraper status — polled on mount + every 30 s ─────────────────
  // Re-polling is necessary because the Overview component stays mounted even
  // while the user is on other tabs, and the reset script can change the KV
  // state at any time.  A stale in-memory snapshot would keep the BLOCKED
  // banner visible long after the status was cleared.
  const [scraperStatus, setScraperStatus] = useState<ScraperStatus | null>(null)
  useEffect(() => {
    let cancelled = false
    const poll = () => {
      fetchScraperStatus()
        .then(s => { if (!cancelled) setScraperStatus(s) })
        .catch(() => { /* non-critical — ignore */ })
    }
    poll()
    const interval = setInterval(poll, 30_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  return (
    <div className="space-y-12">

      {/* ── LinkedIn scraper status banners ──────────────────────────────── */}
      {scraperStatus?.status === 'BLOCKED' && (
        <LinkedInBlockedBanner blockedAt={scraperStatus.blocked_at} />
      )}
      {scraperStatus?.status === 'PAUSED' && (
        <LinkedInPausedBanner />
      )}

      {/* ── Hero greeting ───────────────────────────────────────────────── */}
      <div>
        <h1 className="text-[28px] font-semibold text-slate-900 tracking-tight leading-tight">
          {_timeGreeting()}
          {getGreetingName(displayName ?? '')
            ? `, ${getGreetingName(displayName ?? '')}`
            : ''}
        </h1>
        <p className="text-[14px] text-slate-400 mt-1.5">
          Here&apos;s what happened overnight.
        </p>
      </div>

      {/* ── KPI strip ───────────────────────────────────────────────────── */}
      <section>
        <KPIRow
          jobsScannedToday={jobsScannedToday}
          highMatches={highMatches}
          actionsTaken={actionsTaken}
          loading={jobsLoading}
        />
      </section>

      {/* ── Divider ─────────────────────────────────────────────────────── */}
      <hr className="border-slate-100" />

      {/* ── Confidence Matrix (TrustDashboard) ──────────────────────────── */}
      {/* Remounts on every tab-switch to Overview, so fetchData fires fresh. */}
      <TrustDashboard userId={userId} />

      {/* ── Divider ─────────────────────────────────────────────────────── */}
      <hr className="border-slate-100" />

      {/* ── Quick actions + Top matches — side by side on wide screens ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-12">

        {/* Quick actions */}
        <section>
          <QuickActions
            newCount={jobsScannedToday}
            savedCount={savedIds.length || 3}
            onGo={onGo}
          />
        </section>

        {/* Top matches */}
        <section>
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-[13px] font-semibold uppercase tracking-[0.12em] text-slate-400">
              Top matches today
            </h2>
            <button
              onClick={handleMatchClick}
              className="inline-flex items-center gap-1 text-[12px] text-slate-400 hover:text-slate-700 transition-colors"
            >
              See all <ArrowIcon s={11} />
            </button>
          </div>

          {jobsLoading ? (
            <>
              <TopMatchSkeleton opacity={1}   />
              <TopMatchSkeleton opacity={0.7} />
              <TopMatchSkeleton opacity={0.4} />
            </>
          ) : previewJobs.length > 0 ? (
            previewJobs.map(j => (
              <TopMatchRow
                key={j.job_id}
                job={j}
                onClick={() => handleMatchJobClick(j.job_id)}
              />
            ))
          ) : (
            <p className="py-8 text-[13px] text-slate-400">
              No matches yet — agents are scanning.
            </p>
          )}
        </section>

      </div>
    </div>
  )
}
