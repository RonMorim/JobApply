'use client'

import Link        from 'next/link'
import AuthGuard   from '@/components/AuthGuard'
import { TOKENS }  from '@/lib/tokens'

// ── Trending job seed data ─────────────────────────────────────────────────────

const TRENDING_JOBS = [
  {
    id: '1',
    title: 'Senior Product Manager',
    company: 'Meta',
    location: 'Tel Aviv, IL',
    tags: ['B2C', 'Growth', 'Data-driven'],
    postedAgo: '2h ago',
  },
  {
    id: '2',
    title: 'Product Manager — Payments',
    company: 'Stripe',
    location: 'Remote',
    tags: ['Fintech', 'API', 'B2B'],
    postedAgo: '5h ago',
  },
  {
    id: '3',
    title: 'Group Product Manager',
    company: 'Wix',
    location: 'Tel Aviv, IL',
    tags: ['Platform', 'Leadership'],
    postedAgo: '8h ago',
  },
  {
    id: '4',
    title: 'Product Manager — Mobile',
    company: 'Monday.com',
    location: 'Tel Aviv, IL',
    tags: ['Mobile', 'SaaS', 'B2B'],
    postedAgo: '1d ago',
  },
  {
    id: '5',
    title: 'Technical Product Manager',
    company: 'Cloudinary',
    location: 'Petah Tikva, IL',
    tags: ['Infrastructure', 'APIs'],
    postedAgo: '1d ago',
  },
  {
    id: '6',
    title: 'Principal Product Manager',
    company: 'Check Point',
    location: 'Tel Aviv, IL',
    tags: ['Cybersecurity', 'Enterprise'],
    postedAgo: '2d ago',
  },
]

// ── Sub-components ────────────────────────────────────────────────────────────

function CompanyAvatar({ name }: { name: string }) {
  const initials = name.split(' ').slice(0, 2).map(w => w[0]).join('')
  const hue = name.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360
  return (
    <div
      className="w-10 h-10 rounded-xl flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
      style={{ background: `hsl(${hue},55%,45%)` }}
      aria-hidden="true"
    >
      {initials}
    </div>
  )
}

function ScorePending() {
  return (
    <div
      className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
      style={{ background: 'rgba(148,163,184,0.12)', color: '#64748b', border: '1px solid rgba(148,163,184,0.2)' }}
    >
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </svg>
      Match score pending
    </div>
  )
}

function JobCard({ job }: { job: typeof TRENDING_JOBS[0] }) {
  return (
    <div
      className="bg-white rounded-2xl border border-slate-100 p-5 flex flex-col gap-4 hover:shadow-md transition-shadow"
      style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
    >
      <div className="flex items-start gap-3">
        <CompanyAvatar name={job.company} />
        <div className="flex-1 min-w-0">
          <h3 className="text-[14px] font-semibold text-slate-900 leading-tight truncate">
            {job.title}
          </h3>
          <p className="text-[12px] text-slate-500 mt-0.5">
            {job.company} &middot; {job.location}
          </p>
        </div>
        <span className="text-[11px] text-slate-400 flex-shrink-0 mt-0.5">{job.postedAgo}</span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {job.tags.map(tag => (
          <span
            key={tag}
            className="text-[11px] px-2 py-0.5 rounded-md font-medium"
            style={{ background: 'rgba(20,184,166,0.08)', color: '#0d9488' }}
          >
            {tag}
          </span>
        ))}
      </div>

      <div className="flex items-center justify-between pt-1 border-t border-slate-50">
        <ScorePending />
        <span className="text-[11px] text-slate-400 italic">Complete your profile to unlock</span>
      </div>
    </div>
  )
}

// ── Page content ──────────────────────────────────────────────────────────────

function DiscoverContent() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-100 sticky top-0 z-20">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <span className="text-base font-extrabold tracking-tight text-slate-900">JobApply</span>
          <Link
            href="/onboarding"
            className="text-sm font-semibold text-white px-4 py-2 rounded-lg transition-opacity hover:opacity-90"
            style={{ background: TOKENS.color.primary }}
          >
            Build your profile
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">

        {/* Profile prompt banner */}
        <div
          className="rounded-2xl p-6 flex flex-col sm:flex-row sm:items-center gap-4"
          style={{ background: 'linear-gradient(135deg, #0F172A 0%, #0a1f1c 100%)', border: '1px solid rgba(255,255,255,0.06)' }}
        >
          <div className="flex-1 space-y-1">
            <p className="text-white font-semibold text-[15px]">Your match scores are waiting</p>
            <p className="text-[13px]" style={{ color: '#94a3b8' }}>
              Complete your profile to unlock personalised match scores for every job below.
            </p>
          </div>
          <Link
            href="/onboarding"
            className="flex-shrink-0 text-sm font-semibold px-5 py-2.5 rounded-xl transition-opacity hover:opacity-90 text-center"
            style={{ background: TOKENS.color.primary, color: '#fff' }}
          >
            Complete profile
          </Link>
        </div>

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Trending jobs</h1>
            <p className="text-sm text-slate-500 mt-0.5">Updated daily based on market demand</p>
          </div>
          <span
            className="text-[11px] font-semibold px-2.5 py-1 rounded-full"
            style={{ background: `${TOKENS.color.primary}15`, color: TOKENS.color.primary }}
          >
            {TRENDING_JOBS.length} roles
          </span>
        </div>

        {/* Job grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {TRENDING_JOBS.map(job => <JobCard key={job.id} job={job} />)}
        </div>

      </main>
    </div>
  )
}

// ── Page (guarded) ────────────────────────────────────────────────────────────

export default function DiscoverPage() {
  return (
    <AuthGuard>
      <DiscoverContent />
    </AuthGuard>
  )
}
