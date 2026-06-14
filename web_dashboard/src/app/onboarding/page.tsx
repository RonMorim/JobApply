'use client'

import { useState, useRef } from 'react'
import { useRouter }        from 'next/navigation'
import AuthGuard            from '@/components/AuthGuard'
import { TOKENS }           from '@/lib/tokens'

// ── Icons ─────────────────────────────────────────────────────────────────────

function CheckIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function UploadIcon({ s = 20 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 16 12 12 8 16" /><line x1="12" y1="12" x2="12" y2="21" />
      <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
    </svg>
  )
}

function LinkedInIcon({ s = 20 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="currentColor">
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect x="2" y="9" width="4" height="12" /><circle cx="4" cy="4" r="2" />
    </svg>
  )
}

function SpinnerIcon({ s = 20 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

// ── Steps data ────────────────────────────────────────────────────────────────

const STEPS = [
  {
    icon:  '🗂️',
    title: 'Create your Master Profile',
    body:  'Tell Ariel about your experience once. She stores it all in a persistent profile so you never have to repeat yourself.',
    color: 'teal',
  },
  {
    icon:  '⚡',
    title: 'Auto-Tailor CVs for any job',
    body:  'Paste a job description and get a perfectly tailored, ATS-optimised CV in seconds — with a match-score so you know how strong your application is.',
    color: 'violet',
  },
  {
    icon:  '📊',
    title: 'Track your applications',
    body:  'A Kanban board keeps every application visible. From "Saved" to "Offer", you always know where each opportunity stands.',
    color: 'amber',
  },
]

// ── Page ──────────────────────────────────────────────────────────────────────

type Phase = 'showcase' | 'intake' | 'loading' | 'done'

function OnboardingContent() {
  const router   = useRouter()
  const [phase,  setPhase]  = useState<Phase>('showcase')
  const [active, setActive] = useState(0)
  const fileRef  = useRef<HTMLInputElement>(null)

  // ── Showcase ─────────────────────────────────────────────────────────────────

  if (phase === 'showcase') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-4 py-12"
        style={{ background: 'linear-gradient(135deg, #f0fdfa 0%, #ede9fe 100%)' }}
      >
        {/* Wordmark */}
        <div className="mb-10 text-center">
          <span className="text-[22px] font-extrabold tracking-tight" style={{ color: TOKENS.color.primary }}>
            JobApply
          </span>
          <span className="text-[22px] font-light text-slate-400"> · AI career engine</span>
        </div>

        {/* Step cards */}
        <div className="w-full max-w-3xl grid md:grid-cols-3 gap-5 mb-10">
          {STEPS.map((step, idx) => {
            const isActive = active === idx
            return (
              <button
                key={idx}
                onClick={() => setActive(idx)}
                className={`relative text-left rounded-2xl border p-6 transition-all duration-200 cursor-pointer ${
                  isActive
                    ? 'border-teal-300 bg-white shadow-lg scale-[1.02]'
                    : 'border-slate-200 bg-white/70 hover:bg-white hover:border-slate-300'
                }`}
              >
                {/* Step badge */}
                <div className={`absolute -top-3 -left-3 w-7 h-7 rounded-full flex items-center justify-center text-[12px] font-bold border-2 border-white shadow ${
                  isActive ? 'bg-teal-500 text-white' : 'bg-slate-200 text-slate-500'
                }`}>
                  {idx + 1}
                </div>

                <div className="text-3xl mb-3">{step.icon}</div>
                <p className="text-[15px] font-bold text-slate-900 mb-2 leading-snug">{step.title}</p>
                <p className="text-[13px] text-slate-500 leading-relaxed">{step.body}</p>

                {isActive && (
                  <div className="mt-3 flex items-center gap-1.5 text-[12px] font-semibold text-teal-600">
                    <CheckIcon /> Selected
                  </div>
                )}
              </button>
            )
          })}
        </div>

        {/* Step indicator dots */}
        <div className="flex items-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              className={`rounded-full transition-all ${
                active === i ? 'w-6 h-2.5 bg-teal-500' : 'w-2.5 h-2.5 bg-slate-300'
              }`}
            />
          ))}
        </div>

        {/* CTA */}
        <button
          onClick={() => setPhase('intake')}
          className="h-12 px-8 rounded-2xl text-[15px] font-semibold text-white shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all"
          style={{ background: `linear-gradient(135deg, ${TOKENS.color.primary}, ${TOKENS.color.primaryHover})` }}
        >
          Get Started →
        </button>

        <p className="mt-4 text-[12px] text-slate-400">No credit card required · Takes 3 minutes</p>
      </div>
    )
  }

  // ── Intake hub ───────────────────────────────────────────────────────────────

  const handleImport = async (source: 'cv' | 'linkedin') => {
    setPhase('loading')
    await new Promise(r => setTimeout(r, 2000))  // mocked 2-second processing
    setPhase('done')
    setTimeout(() => router.push('/profile-builder'), 800)
  }

  if (phase === 'loading') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4"
        style={{ background: 'linear-gradient(135deg, #f0fdfa 0%, #ede9fe 100%)' }}
      >
        <SpinnerIcon s={36} />
        <p className="text-[15px] font-semibold text-slate-700">Analysing your profile…</p>
        <p className="text-[13px] text-slate-400">Hang tight — this only takes a moment.</p>
      </div>
    )
  }

  if (phase === 'done') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3"
        style={{ background: 'linear-gradient(135deg, #f0fdfa 0%, #ede9fe 100%)' }}
      >
        <div className="w-14 h-14 rounded-full bg-teal-500 text-white flex items-center justify-center text-2xl shadow-lg">
          ✓
        </div>
        <p className="text-[16px] font-bold text-slate-900">Profile Draft Created</p>
        <p className="text-[13px] text-slate-500">Launching Ariel…</p>
      </div>
    )
  }

  // intake phase
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-12"
      style={{ background: 'linear-gradient(135deg, #f0fdfa 0%, #ede9fe 100%)' }}
    >
      <div className="w-full max-w-md">
        {/* Back */}
        <button
          onClick={() => setPhase('showcase')}
          className="text-[13px] text-slate-400 hover:text-slate-700 mb-6 flex items-center gap-1 transition"
        >
          ← Back
        </button>

        <div className="bg-white rounded-3xl shadow-xl p-8">
          <h2 className="text-[20px] font-bold text-slate-900 mb-1">Import your existing profile</h2>
          <p className="text-[13.5px] text-slate-500 mb-7 leading-relaxed">
            Skip the blank slate — let us read your current CV or LinkedIn profile to build
            your Master Profile in seconds.
          </p>

          {/* Upload CV */}
          <button
            onClick={() => fileRef.current?.click()}
            className="w-full flex items-center gap-4 rounded-2xl border-2 border-dashed border-slate-200 p-5 hover:border-teal-400 hover:bg-teal-50 transition text-left group"
          >
            <div className="w-11 h-11 rounded-xl bg-slate-100 group-hover:bg-teal-100 flex items-center justify-center text-slate-500 group-hover:text-teal-600 flex-shrink-0 transition">
              <UploadIcon s={20} />
            </div>
            <div>
              <p className="text-[14px] font-semibold text-slate-800">Upload existing CV</p>
              <p className="text-[12px] text-slate-400 mt-0.5">PDF, DOCX — max 10 MB</p>
            </div>
          </button>

          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={() => handleImport('cv')}
          />

          {/* Divider */}
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-slate-100" />
            <span className="text-[12px] text-slate-400 font-medium">or</span>
            <div className="flex-1 h-px bg-slate-100" />
          </div>

          {/* LinkedIn */}
          <button
            onClick={() => handleImport('linkedin')}
            className="w-full flex items-center gap-4 rounded-2xl border-2 border-dashed border-slate-200 p-5 hover:border-blue-400 hover:bg-blue-50 transition text-left group"
          >
            <div className="w-11 h-11 rounded-xl bg-slate-100 group-hover:bg-blue-100 flex items-center justify-center text-slate-500 group-hover:text-blue-600 flex-shrink-0 transition">
              <LinkedInIcon s={20} />
            </div>
            <div>
              <p className="text-[14px] font-semibold text-slate-800">Connect LinkedIn</p>
              <p className="text-[12px] text-slate-400 mt-0.5">Import your work history automatically</p>
            </div>
          </button>

          {/* Skip */}
          <button
            onClick={() => router.push('/profile-builder')}
            className="w-full mt-6 text-[13px] text-slate-400 hover:text-slate-600 transition"
          >
            Skip — I'll build my profile with Ariel instead
          </button>
        </div>
      </div>
    </div>
  )
}

export default function OnboardingPage() {
  return (
    <AuthGuard>
      <OnboardingContent />
    </AuthGuard>
  )
}
