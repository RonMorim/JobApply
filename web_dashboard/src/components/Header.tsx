'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { TOKENS } from '@/lib/tokens'
import { Logo } from './ui/Logo'
import { StatusDot } from './ui/StatusDot'
import { BellIcon, SlidersIcon, ChevIcon, MailIcon } from './icons'
import { EmailSetupModal } from './EmailSetupModal'
import { useAuth } from '@/contexts/AuthContext'
import { useChat } from '@/contexts/ChatContext'
import { resolveDisplayName, getInitials } from '@/lib/nameUtils'
import type { Job } from '@/lib/data'

function HelpIcon({ s = 15 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

export type Tab = 'overview' | 'apps' | 'feed'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview'     },
  { id: 'feed',     label: 'Matches'      },
  { id: 'apps',     label: 'Applications' },
]

interface HeaderProps {
  tab?:            Tab
  setTab?:         (t: Tab) => void
  onOpenControls?: () => void
  jobs?:           Job[]
}

export function Header({ tab, setTab, onOpenControls, jobs = [] }: HeaderProps) {
  const [menuOpen,    setMenuOpen]    = useState(false)
  const [bellOpen,    setBellOpen]    = useState(false)
  const [emailModal,  setEmailModal]  = useState(false)
  const router    = useRouter()
  const pathname  = usePathname()
  const bellRef   = useRef<HTMLDivElement>(null)

  const { user, signOut } = useAuth()
  const { openEliya, isEliyaOpen } = useChat()
  const displayName = resolveDisplayName(user?.email, user?.user_metadata as Record<string, unknown> | null)
  const initials    = getInitials(displayName)

  const highMatchJobs = jobs.filter(j => j.score >= 85)
  const hasHighMatch  = highMatchJobs.length > 0

  // Close bell dropdown when clicking outside
  useEffect(() => {
    if (!bellOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [bellOpen])

  // Suppress tab underlines on any route that isn't the main dashboard.
  const onMainDashboard   = pathname === '/'
  const onAnalytics       = pathname === '/analytics'
  const onCapabilities    = pathname === '/capabilities'
  const activeTab         = onMainDashboard ? (tab ?? null) : null

  return (
    <>
    <EmailSetupModal open={emailModal} onClose={() => setEmailModal(false)} />

    <header className="w-full bg-white border-b border-slate-100 sticky top-0 z-40">
      <div className="max-w-[1920px] mx-auto px-12 h-[60px] grid grid-cols-[auto_1fr_auto] items-center gap-8">

      <Logo />

      {/* Primary nav — centered, text-only with bottom-border active indicator */}
      <nav className="hidden md:flex items-center justify-center space-x-10 text-sm font-medium text-slate-400 h-full">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => {
              // Encode the tab in the URL so it survives any auth-cycle redirect.
              // searchParams.get('tab') has priority over localStorage in page.tsx,
              // so even if localStorage is wiped by _onAuthError the user lands back
              // on the correct tab rather than defaulting to 'overview'.
              router.push(`/?tab=${t.id}`)
              setTab?.(t.id)
            }}
            className={`h-full pb-0 border-b-2 transition-colors ${
              activeTab === t.id
                ? 'text-slate-900 border-slate-900'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            {t.label}
          </button>
        ))}
        <Link
          href="/capabilities"
          className={`h-full inline-flex items-center border-b-2 transition-colors ${
            onCapabilities ? 'text-slate-900 border-slate-900' : 'border-transparent hover:text-slate-900'
          }`}
        >
          Capabilities
        </Link>
        <Link
          href="/analytics"
          className={`h-full inline-flex items-center border-b-2 transition-colors ${
            onAnalytics ? 'text-slate-900 border-slate-900' : 'border-transparent hover:text-slate-900'
          }`}
        >
          Analytics
        </Link>
      </nav>

      {/* Right-side utility cluster */}
      <div className="flex items-center gap-3 justify-end">
        {pathname === '/' && tab === 'feed' && onOpenControls && (
          <button
            onClick={onOpenControls}
            className="inline-flex items-center gap-1.5 h-7 px-3 rounded-md text-[12.5px] font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-50 border border-slate-200 transition"
          >
            <SlidersIcon s={14} /> Preferences
          </button>
        )}

        {/* Help — opens Eliya support chat (indigo theme) */}
        <button
          onClick={openEliya}
          title="Help & Support — Ask Eliya"
          aria-label="Help & Support"
          className="inline-flex items-center justify-center w-8 h-8 rounded-md transition"
          style={
            isEliyaOpen
              ? { color: '#4F46E5', background: '#EEF2FF' }
              : { color: '#94a3b8' }
          }
          onMouseEnter={e => { if (!isEliyaOpen) (e.currentTarget as HTMLButtonElement).style.color = '#4F46E5'; (e.currentTarget as HTMLButtonElement).style.background = '#EEF2FF' }}
          onMouseLeave={e => { if (!isEliyaOpen) { (e.currentTarget as HTMLButtonElement).style.color = ''; (e.currentTarget as HTMLButtonElement).style.background = '' } }}
        >
          <HelpIcon s={16} />
        </button>

        <button
          onClick={() => setEmailModal(true)}
          className="inline-flex items-center justify-center w-8 h-8 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-50 transition"
          title="Connect Email Automation"
        >
          <MailIcon s={15} />
        </button>

        {/* Bell */}
        <div className="relative" ref={bellRef}>
          <button
            onClick={() => { setMenuOpen(false); setBellOpen(v => !v) }}
            title="Notifications"
            className="inline-flex items-center justify-center w-8 h-8 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-50 transition"
          >
            <BellIcon s={16} />
          </button>
          {hasHighMatch && (
            <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-rose-500 ring-2 ring-white pointer-events-none" />
          )}

          {bellOpen && (
            <div
              className="absolute right-0 top-11 w-72 rounded-xl bg-white border border-slate-100 overflow-hidden z-50"
              style={{ boxShadow: 'var(--ja-floating)' }}
            >
              <div className="px-3 py-2.5 border-b border-slate-50 flex items-center justify-between">
                <span className="text-[12px] font-semibold text-slate-700">High-match alerts</span>
                {highMatchJobs.length > 0 && (
                  <span className="text-[10.5px] font-semibold text-rose-600 bg-rose-50 border border-rose-200 px-1.5 py-0.5 rounded-md">
                    {highMatchJobs.length}
                  </span>
                )}
              </div>
              {highMatchJobs.length === 0 ? (
                <p className="px-3 py-4 text-[12.5px] text-slate-400 text-center">
                  No high-match jobs yet (≥ 85).
                </p>
              ) : (
                <ul className="max-h-72 overflow-y-auto divide-y divide-slate-50">
                  {highMatchJobs.map(job => (
                    <li key={job.id}>
                      <button
                        onClick={() => setBellOpen(false)}
                        className="w-full text-left px-3 py-2.5 hover:bg-slate-50 transition flex items-center justify-between gap-3"
                      >
                        <div className="min-w-0">
                          <p className="text-[12.5px] font-semibold text-slate-900 truncate">{job.title}</p>
                          <p className="text-[11.5px] text-slate-500 truncate">{job.company}</p>
                        </div>
                        <span className="shrink-0 text-[11.5px] font-bold tabular-nums px-2 py-0.5 rounded-lg bg-teal-50 text-teal-700">
                          {Math.round(job.score)}%
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* User avatar + menu */}
        <div className="relative">
          <button
            onClick={() => { setBellOpen(false); setMenuOpen(v => !v) }}
            className="w-8 h-8 rounded-md bg-slate-100 text-slate-600 flex items-center justify-center text-xs font-bold hover:bg-slate-200 transition"
          >
            {initials}
          </button>

          {menuOpen && (
            <div
              onMouseLeave={() => setMenuOpen(false)}
              className="absolute right-0 top-10 w-56 rounded-xl bg-white border border-slate-100 overflow-hidden z-50"
              style={{ boxShadow: 'var(--ja-floating)' }}
            >
              <div className="px-3 py-3 border-b border-slate-50">
                <div className="text-[13px] font-semibold text-slate-900">{displayName}</div>
                <div className="text-[12px] text-slate-400">{user?.email ?? ''}</div>
              </div>
              <button
                onClick={() => { setMenuOpen(false); router.push('/profile-builder') }}
                className="w-full text-left px-3 py-2.5 text-[13px] font-semibold flex items-center gap-2 hover:bg-violet-50 text-violet-700 border-b border-slate-50"
              >
                <span className="text-base leading-none">✦</span>
                AI Profile Builder
              </button>
              <button className="w-full text-left px-3 py-2 text-[13px] text-slate-700 hover:bg-slate-50 transition">
                Profile & preferences
              </button>
              <div className="border-t border-slate-200" />
              {process.env.NODE_ENV === 'development' && (
                <button
                  onClick={async () => {
                    setMenuOpen(false)
                    await signOut()
                  }}
                  className="w-full text-left px-3 py-2 text-[11.5px] font-mono text-amber-700 hover:bg-amber-50 transition flex items-center gap-1.5"
                  title="Clears all Supabase session storage and forces a clean re-login — use to switch between user profiles in dev"
                >
                  <span className="text-[10px] bg-amber-100 text-amber-600 font-bold px-1 rounded">DEV</span>
                  Force Reset Session
                </button>
              )}
              <button
                onClick={() => { setMenuOpen(false); void signOut() }}
                className="w-full text-left px-3 py-2 text-[13px] text-rose-600 hover:bg-rose-50 transition"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>

      </div>
    </header>
    </>
  )
}
