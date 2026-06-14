'use client'
import { useState, useCallback } from 'react'
import { fetchAtsKeywords } from '@/lib/api'
import type { AtsKeywordsResponse } from '@/lib/apiTypes'

// ── Helpers ───────────────────────────────────────────────────────────────────

function CopyIcon({ s = 13 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function SpinnerIcon({ s = 14 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

// ── Keyword pill ──────────────────────────────────────────────────────────────

function Pill({
  label,
  variant,
}: {
  label:   string
  variant: 'present' | 'missing'
}) {
  return (
    <span
      className={`inline-flex items-center h-6 px-2.5 rounded-full text-[11.5px] font-medium border ${
        variant === 'present'
          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
          : 'bg-amber-50 text-amber-700 border-amber-200'
      }`}
    >
      {variant === 'present' ? '✓ ' : '+ '}
      {label}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  jobId:    string
  hasJd:    boolean  // whether JD text is available — show hint if not
}

export function AtsKeywordsPanel({ jobId, hasJd }: Props) {
  const [data,       setData]       = useState<AtsKeywordsResponse | null>(null)
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState<string | null>(null)
  const [copiedList, setCopiedList] = useState<'missing' | null>(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchAtsKeywords(jobId)
      setData(result)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg.includes('400') ? 'Fetch the full JD first (click "Details → Load Description").' : msg)
    } finally {
      setLoading(false)
    }
  }, [jobId])

  const copyMissing = useCallback(() => {
    if (!data?.missing.length) return
    navigator.clipboard.writeText(data.missing.join(', ')).then(() => {
      setCopiedList('missing')
      setTimeout(() => setCopiedList(null), 2000)
    })
  }, [data])

  // ── No JD available ────────────────────────────────────────────────────────
  if (!hasJd && !data) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-[12.5px] text-slate-500 flex items-center gap-2">
        <span className="text-slate-300 text-base">⚠</span>
        Fetch the full job description first to run ATS keyword analysis.
      </div>
    )
  }

  // ── Initial state ──────────────────────────────────────────────────────────
  if (!data && !loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-[12.5px] font-semibold text-slate-700">ATS Keyword Gap Analysis</p>
            <p className="text-[11.5px] text-slate-400 mt-0.5">
              Find which JD keywords are missing from your LinkedIn profile.
            </p>
          </div>
          <button
            onClick={run}
            className="h-8 px-3 rounded-lg text-[12px] font-semibold border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition flex items-center gap-1.5"
          >
            ✦ Analyse
          </button>
        </div>
      </div>
    )
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white px-4 py-4 flex items-center gap-2 text-[12.5px] text-slate-500">
        <SpinnerIcon /> Extracting ATS keywords…
      </div>
    )
  }

  // ── Error ──────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[12.5px] text-red-700 flex items-center justify-between gap-3">
        <span>{error}</span>
        <button onClick={run} className="text-red-500 hover:text-red-700 text-[11px] underline">Retry</button>
      </div>
    )
  }

  if (!data) return null

  const coverage = data.jd_keywords.length
    ? Math.round((data.present.length / data.jd_keywords.length) * 100)
    : 0

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[12.5px] font-semibold text-slate-700">ATS Keyword Gap</span>
          {/* Coverage meter */}
          <div className="flex items-center gap-1.5">
            <div className="w-24 h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  coverage >= 70 ? 'bg-emerald-400' : coverage >= 40 ? 'bg-amber-400' : 'bg-red-400'
                }`}
                style={{ width: `${coverage}%` }}
              />
            </div>
            <span className={`text-[11px] font-semibold tabular-nums ${
              coverage >= 70 ? 'text-emerald-600' : coverage >= 40 ? 'text-amber-600' : 'text-red-600'
            }`}>
              {coverage}%
            </span>
          </div>
        </div>
        <button
          onClick={run}
          className="text-[11px] text-slate-400 hover:text-slate-600 underline"
        >
          Refresh
        </button>
      </div>

      <div className="px-4 py-4 flex flex-col gap-4">
        {/* Missing keywords — action items */}
        {data.missing.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[11.5px] font-semibold text-amber-700">
                Missing from LinkedIn ({data.missing.length}) — add these to your Skills section
              </p>
              <button
                onClick={copyMissing}
                className={`flex items-center gap-1 text-[11px] font-medium border rounded-lg h-6 px-2 transition ${
                  copiedList === 'missing'
                    ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                    : 'border-amber-200 bg-amber-50 text-amber-700 hover:border-amber-300'
                }`}
              >
                <CopyIcon s={11} />
                {copiedList === 'missing' ? 'Copied!' : 'Copy list'}
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {data.missing.map(kw => (
                <Pill key={kw} label={kw} variant="missing" />
              ))}
            </div>
          </div>
        )}

        {/* Present keywords */}
        {data.present.length > 0 && (
          <div>
            <p className="text-[11.5px] font-semibold text-emerald-700 mb-2">
              Already in your profile ({data.present.length}) ✓
            </p>
            <div className="flex flex-wrap gap-1.5">
              {data.present.map(kw => (
                <Pill key={kw} label={kw} variant="present" />
              ))}
            </div>
          </div>
        )}

        {data.missing.length === 0 && (
          <p className="text-[12.5px] text-emerald-700 font-semibold">
            ✓ Full keyword coverage — your profile matches all extracted ATS keywords.
          </p>
        )}
      </div>
    </div>
  )
}
