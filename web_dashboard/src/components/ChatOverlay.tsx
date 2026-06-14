'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { useChat }   from '@/contexts/ChatContext'
import type { ChatMessage } from '@/contexts/ChatContext'
import { useAuth }   from '@/contexts/AuthContext'
import { TOKENS }    from '@/lib/tokens'

// ── Session-ID helpers (public/anonymous mode only) ───────────────────────────

const PUBLIC_SESSION_KEY = 'jobapply_public_session_id'

function getOrCreateSessionId(): string {
  if (typeof window === 'undefined') return ''
  try {
    const stored = localStorage.getItem(PUBLIC_SESSION_KEY)
    if (stored && /^[0-9a-f-]{36}$/i.test(stored)) return stored
    const id = crypto.randomUUID()
    localStorage.setItem(PUBLIC_SESSION_KEY, id)
    return id
  } catch {
    return crypto.randomUUID()
  }
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function CloseIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg width={13} height={13} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
      style={{ animation: 'chat-spin 0.8s linear infinite', flexShrink: 0 }}>
      <style>{`@keyframes chat-spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

// ── Markdown-lite renderer ────────────────────────────────────────────────────

function renderInline(text: string, key?: number): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/)
  return (
    <span key={key}>
      {parts.map((p, i) =>
        p.startsWith('**') && p.endsWith('**')
          ? <strong key={i} className="font-semibold text-slate-900">{p.slice(2, -2)}</strong>
          : <span key={i}>{p}</span>
      )}
    </span>
  )
}

function renderMarkdown(text: string): React.ReactNode {
  const paragraphs = text.split('\n\n').filter(Boolean)
  return paragraphs.map((para, pi) => {
    const lines = para.split('\n')
    if (lines.every(l => l.startsWith('- ') || l.startsWith('* ') || l.startsWith('• '))) {
      return (
        <ul key={pi} className="space-y-1 mb-2">
          {lines.map((l, li) => (
            <li key={li} className="flex items-start gap-1.5">
              <span className="mt-[6px] shrink-0 w-[4px] h-[4px] rounded-full bg-slate-400" />
              <span className="flex-1">{renderInline(l.replace(/^[-*•]\s+/, ''))}</span>
            </li>
          ))}
        </ul>
      )
    }
    return <p key={pi} className="mb-2 last:mb-0">{lines.map(renderInline)}</p>
  })
}

// ── Tool-call Action Card (authenticated mode only) ───────────────────────────

const TOOL_LABELS: Record<string, string> = {
  tailor_resume_for_job: 'Resume Tailoring Triggered',
}

interface ActionCardProps {
  toolName:  string
  toolArgs:  Record<string, unknown>
  onConfirm: () => void
  onDismiss: () => void
}

function ActionCard({ toolName, toolArgs, onConfirm, onDismiss }: ActionCardProps) {
  const [dismissed, setDismissed] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  if (dismissed) return null

  const heading  = TOOL_LABELS[toolName] ?? toolName
  const jobTitle = typeof toolArgs.job_title === 'string' ? toolArgs.job_title : ''
  const company  = typeof toolArgs.company   === 'string' ? toolArgs.company   : ''
  const skills   = Array.isArray(toolArgs.focus_skills)
    ? (toolArgs.focus_skills as unknown[]).filter((s): s is string => typeof s === 'string')
    : []

  return (
    <div className="bg-white border border-slate-100 rounded-xl shadow-sm overflow-hidden">
      <div className="h-0.5 w-full" style={{ background: TOKENS.color.primary }} />
      <div className="px-4 py-3.5 space-y-3">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center justify-center w-6 h-6 rounded-md text-white text-[11px] font-bold shrink-0"
            style={{ background: TOKENS.color.primary }}
          >
            AI
          </span>
          <p className="text-[12.5px] font-semibold text-slate-900 leading-tight">{heading}</p>
        </div>
        {(jobTitle || company) && (
          <div className="text-[12px] text-slate-600">
            <span className="font-medium text-slate-800">{jobTitle}</span>
            {company && <span className="text-slate-400"> &middot; {company}</span>}
          </div>
        )}
        {skills.length > 0 && (
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Focus skills</p>
            <div className="flex flex-wrap gap-1.5">
              {skills.map((s, i) => (
                <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-50 border border-slate-200 text-[11px] font-medium text-slate-700">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {confirmed ? (
          <p className="text-[11.5px] font-medium text-teal-700 flex items-center gap-1.5">
            <CheckIcon /> Tailoring started - check the Matches feed.
          </p>
        ) : (
          <div className="flex items-center gap-2 pt-0.5">
            <button
              onClick={() => { setConfirmed(true); onConfirm() }}
              className="flex-1 h-8 rounded-lg text-white text-[11.5px] font-semibold tracking-wide transition active:scale-[0.97]"
              style={{ background: TOKENS.color.primary }}
            >
              Confirm &amp; Generate
            </button>
            <button
              onClick={() => { setDismissed(true); onDismiss() }}
              className="h-8 px-3 rounded-lg text-[11.5px] font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-50 transition"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Message bubble ────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  message:       ChatMessage
  onToolConfirm: (toolName: string, toolArgs: Record<string, unknown>) => void
  onToolDismiss: () => void
}

function MessageBubble({ message, onToolConfirm, onToolDismiss }: MessageBubbleProps) {
  const { role, content, isToolCall, toolName, toolArgs } = message

  if (isToolCall && toolName && toolArgs) {
    return (
      <ActionCard
        toolName={toolName}
        toolArgs={toolArgs}
        onConfirm={() => onToolConfirm(toolName, toolArgs)}
        onDismiss={onToolDismiss}
      />
    )
  }

  if (role === 'system') {
    return (
      <div className="flex justify-center">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 text-slate-500 text-[11px] border border-slate-200">
          {content}
        </span>
      </div>
    )
  }

  const isUser = role === 'user'
  if (isUser && content.startsWith("I'm looking at ")) return null

  return (
    <div className={`flex items-end ${isUser ? 'justify-end' : 'justify-start'}`}>
      {/* No per-bubble avatar — identity is established in the panel header */}
      <div
        dir="auto"
        className={`max-w-[82%] rounded-2xl px-3.5 py-2.5 text-[12.5px] leading-relaxed ${
          isUser
            ? 'rounded-br-sm text-white'
            : 'rounded-bl-sm bg-slate-50 border border-slate-100 text-slate-700'
        }`}
        style={isUser ? { background: TOKENS.color.primary } : undefined}
      >
        {isUser ? content : renderMarkdown(content)}
      </div>
    </div>
  )
}

// ── Typing indicator ──────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex items-end justify-start">
      <div className="bg-slate-50 border border-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1">
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-slate-300"
            style={{ animation: `chat-bounce 1.2s ease-in-out ${i * 0.2}s infinite` }}
          />
        ))}
        <style>{`
          @keyframes chat-bounce {
            0%, 80%, 100% { transform: translateY(0); }
            40%           { transform: translateY(-5px); }
          }
        `}</style>
      </div>
    </div>
  )
}

// ── Context pill (authenticated mode) ────────────────────────────────────────

function ContextPill({ topic }: { topic: string }) {
  return (
    <div className="px-4 py-2.5 border-b border-slate-800/40">
      <div
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px]"
        style={{ background: 'rgba(13,148,136,0.18)', border: '1px solid rgba(13,148,136,0.35)' }}
      >
        <span style={{ color: '#5eead4' }}>AI</span>
        <span style={{ color: '#99f6e4' }} className="font-medium truncate">{topic}</span>
      </div>
    </div>
  )
}

// ── Eliya colour tokens (indigo "Support" theme) ──────────────────────────────
const ELIYA = {
  primary:     '#4F46E5',   // indigo-600
  primaryHover:'#4338CA',   // indigo-700
  primarySoft: '#EEF2FF',   // indigo-50
  ring:        'rgba(79,70,229,0.20)',
  border:      '#C7D2FE',   // indigo-200
}

// ── Public (Eliya) chat panel ─────────────────────────────────────────────────
//
// Used when the visitor is NOT authenticated.  Maintains its own local message
// state, calls /api/chat/public, and tracks a persistent anonymous session_id.

function PublicChatPanel({ onClose }: { onClose: () => void }) {
  const [messages,  setMessages]  = useState<ChatMessage[]>([])
  const [draft,     setDraft]     = useState('')
  const [thinking,  setThinking]  = useState(false)
  const [sessionId, setSessionId] = useState('')
  const bottomRef   = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Resolve / create the anonymous session ID once on mount (client only)
  useEffect(() => {
    setSessionId(getOrCreateSessionId())
    setTimeout(() => textareaRef.current?.focus(), 300)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, thinking])

  const handleSend = useCallback(async () => {
    const text = draft.trim()
    if (!text || thinking || !sessionId) return

    const userMsg: ChatMessage = { role: 'user', content: text, ts: Date.now() }
    // Snapshot current messages for history before state update
    const historySnapshot = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(({ role, content }) => ({ role: role as 'user' | 'assistant', content }))

    setMessages(prev => [...prev, userMsg])
    setDraft('')
    setThinking(true)

    const assistantTs = Date.now()
    let streamStarted = false
    let accumulated   = ''

    try {
      const res = await fetch('/api/chat/public', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          session_id: sessionId,
          message:    text,
          history:    historySnapshot,
        }),
      })

      if (!res.ok || !res.body) {
        // Non-streaming error response
        const errData = await res.json().catch(() => ({})) as { error?: string }
        throw new Error(errData.error ?? `HTTP ${res.status}`)
      }

      const reader     = res.body.getReader()
      const decoder    = new TextDecoder()
      let   lineBuffer = ''

      outer: while (true) {
        const { done, value } = await reader.read()
        if (done) break

        lineBuffer += decoder.decode(value, { stream: true })
        const events = lineBuffer.split('\n\n')
        lineBuffer   = events.pop() ?? ''

        for (const event of events) {
          for (const line of event.split('\n')) {
            if (!line.startsWith('data:')) continue
            const payload = line.slice(5).trim()
            if (payload === '[DONE]') break outer

            let parsed: { chunk?: string; error?: string }
            try { parsed = JSON.parse(payload) as typeof parsed }
            catch { continue }

            if (parsed.error) throw new Error(parsed.error)
            if (!parsed.chunk) continue

            accumulated += parsed.chunk

            if (!streamStarted) {
              streamStarted = true
              setThinking(false)
              setMessages(prev => [
                ...prev,
                { role: 'assistant', content: accumulated, ts: assistantTs },
              ])
            } else {
              setMessages(prev => {
                const next = [...prev]
                next[next.length - 1] = { ...next[next.length - 1], content: accumulated }
                return next
              })
            }
          }
        }
      }

      if (!streamStarted) {
        setMessages(prev => [...prev, {
          role: 'assistant', content: '_(No response received.)_', ts: assistantTs,
        }])
      }

    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const msg = err instanceof Error ? err.message : 'Something went wrong. Please try again.'
      setMessages(prev => [...prev, { role: 'assistant', content: msg, ts: Date.now() }])
    } finally {
      setThinking(false)
    }
  }, [draft, thinking, sessionId, messages])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const handleDraftChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDraft(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
  }

  return (
    <>
      {/* Header — indigo Support theme */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-3" style={{ background: '#1e1b4b' }}>
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold text-white"
            style={{ background: ELIYA.primary }}
          >
            E
          </div>
          <div>
            <p className="text-[13px] font-semibold text-white leading-tight">Eliya</p>
            <p className="text-[10.5px] leading-tight" style={{ color: '#a5b4fc' }}>Support &amp; Onboarding</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              title="Clear conversation"
              className="w-7 h-7 flex items-center justify-center rounded-lg transition"
              style={{ color: '#6366f1' }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(99,102,241,0.15)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
            >
              <TrashIcon />
            </button>
          )}
          <button
            onClick={onClose}
            title="Close"
            className="w-7 h-7 flex items-center justify-center rounded-lg transition"
            style={{ color: '#6366f1' }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(99,102,241,0.15)' }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
          >
            <CloseIcon />
          </button>
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto bg-white px-4 py-4 space-y-3 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center pb-4">
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center text-white text-lg font-bold"
              style={{ background: ELIYA.primary }}
            >
              E
            </div>
            <p className="text-[13px] font-semibold text-slate-700">Hi, I&apos;m Eliya</p>
            <p className="text-[12px] text-slate-400 leading-relaxed max-w-[240px]">
              Ask me anything about JobApply and I&apos;ll help you get started.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            message={msg}
            onToolConfirm={() => {}}
            onToolDismiss={() => {}}
          />
        ))}

        {thinking && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Input bar — indigo theme */}
      <div className="flex-shrink-0 border-t bg-white px-3 py-2.5 flex items-end gap-2" style={{ borderColor: ELIYA.border }}>
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={handleDraftChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask Eliya anything…"
          dir="auto"
          rows={1}
          disabled={thinking}
          className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none transition disabled:opacity-50 min-h-[44px] max-h-[120px]"
          style={{ lineHeight: '1.5' }}
          onFocus={e => { e.currentTarget.style.borderColor = ELIYA.primary; e.currentTarget.style.boxShadow = `0 0 0 2px ${ELIYA.ring}` }}
          onBlur={e =>  { e.currentTarget.style.borderColor = ''; e.currentTarget.style.boxShadow = '' }}
        />
        <button
          onClick={handleSend}
          disabled={!draft.trim() || thinking}
          title="Send (Enter)"
          className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-white transition active:scale-95 disabled:opacity-35 disabled:pointer-events-none"
          style={{ background: ELIYA.primary }}
        >
          {thinking ? <SpinnerIcon /> : <SendIcon />}
        </button>
      </div>
    </>
  )
}

// ── Authenticated chat panel (Ariel — teal Career Agent theme) ───────────────

function AuthChatPanel({ onClose }: { onClose: () => void }) {
  const { jobContext, messages, thinking, sendMessage, clearMessages } = useChat()
  const [draft,      setDraft]      = useState('')
  const [attachment, setAttachment] = useState<{ name: string; dataUrl: string } | null>(null)
  const bottomRef   = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileRef     = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = ev => setAttachment({ name: file.name, dataUrl: ev.target?.result as string })
    reader.readAsDataURL(file)
    e.target.value = ''
  }

  const handleToolConfirm = useCallback((toolName: string, toolArgs: Record<string, unknown>) => {
    if (toolName === 'tailor_resume_for_job') {
      const title = typeof toolArgs.job_title === 'string' ? toolArgs.job_title : 'this role'
      sendMessage(`Yes, please tailor my CV for ${title}.`)
    }
  }, [sendMessage])

  const handleToolDismiss = useCallback(() => {
    sendMessage('Actually, skip the CV tailoring for now.')
  }, [sendMessage])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, thinking])

  useEffect(() => {
    setTimeout(() => textareaRef.current?.focus(), 300)
  }, [])

  const handleSend = useCallback(() => {
    const text = draft.trim()
    if (!text && !attachment) return
    const payload = attachment
      ? `[Attachment: ${attachment.name}]\n${text}`
      : text
    sendMessage(payload)
    setDraft('')
    setAttachment(null)
  }, [draft, attachment, sendMessage])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const handleDraftChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDraft(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
  }

  return (
    <>
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 bg-slate-900">
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold text-white"
            style={{ background: TOKENS.color.primary }}
          >
            A
          </div>
          <div>
            <p className="text-[13px] font-semibold text-white leading-tight">Ariel</p>
            <p className="text-[10.5px] text-slate-400 leading-tight">Your Career Agent</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              onClick={clearMessages}
              title="Clear conversation"
              className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition"
            >
              <TrashIcon />
            </button>
          )}
          <button
            onClick={onClose}
            title="Close"
            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition"
          >
            <CloseIcon />
          </button>
        </div>
      </div>

      {jobContext && <ContextPill topic={jobContext.topic} />}

      {/* Message list */}
      <div className="flex-1 overflow-y-auto bg-white px-4 py-4 space-y-3 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center pb-4">
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center text-white text-xl font-bold"
              style={{ background: TOKENS.color.primary }}
            >
              A
            </div>
            <p className="text-[13px] font-semibold text-slate-700">Hi, I&apos;m Ariel</p>
            <p className="text-[12px] text-slate-400 leading-relaxed max-w-[240px]">
              I can help you bridge skill gaps, tailor your CV, or prep for interviews.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            message={msg}
            onToolConfirm={handleToolConfirm}
            onToolDismiss={handleToolDismiss}
          />
        ))}

        {thinking && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="flex-shrink-0 border-t border-slate-100 bg-white px-3 py-2.5 space-y-1.5">
        {/* Attachment preview chip */}
        {attachment && (
          <div className="flex items-center gap-2 px-1">
            {attachment.dataUrl.startsWith('data:image') && (
              <img src={attachment.dataUrl} alt="" className="w-6 h-6 rounded object-cover border border-slate-200 shrink-0" />
            )}
            <span className="text-[11px] text-slate-600 flex-1 truncate">{attachment.name}</span>
            <button
              onClick={() => setAttachment(null)}
              className="text-slate-400 hover:text-slate-700 text-[13px] transition"
            >×</button>
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* Hidden file input */}
          <input
            ref={fileRef}
            type="file"
            accept="image/*,.pdf,.txt,.py,.js,.ts,.java,.go,.rs,.cpp,.c,.cs"
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Paperclip button */}
          <button
            onClick={() => fileRef.current?.click()}
            title="Attach a file or screenshot"
            className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          >
            <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66L9.41 17.41a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
            </svg>
          </button>

          <textarea
            ref={textareaRef}
            value={draft}
            onChange={handleDraftChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask Ariel about this job or your CV..."
            dir="auto"
            rows={1}
            disabled={thinking}
            className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-teal-400 focus:ring-2 focus:ring-teal-500/20 transition disabled:opacity-50 min-h-[44px] max-h-[120px]"
            style={{ lineHeight: '1.5' }}
          />
          <button
            onClick={handleSend}
            disabled={(!draft.trim() && !attachment) || thinking}
            title="Send (Enter)"
            className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-white transition active:scale-95 disabled:opacity-35 disabled:pointer-events-none"
            style={{ background: TOKENS.color.primary }}
          >
            {thinking ? <SpinnerIcon /> : <SendIcon />}
          </button>
        </div>
      </div>
    </>
  )
}

// ── Overlay shell helper ──────────────────────────────────────────────────────

function OverlayShell({
  isOpen,
  onBackdropClick,
  offsetRight = '1.5rem',
  ariaLabel,
  shadowColor = 'rgba(15,23,42,0.20)',
  children,
}: {
  isOpen:          boolean
  onBackdropClick: () => void
  offsetRight?:    string
  ariaLabel:       string
  shadowColor?:    string
  children:        React.ReactNode
}) {
  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px] sm:hidden"
          onClick={onBackdropClick}
        />
      )}
      <div
        role="dialog"
        aria-label={ariaLabel}
        aria-modal="true"
        className="fixed bottom-0 right-0 z-50 flex flex-col w-full sm:w-[380px] sm:bottom-6 sm:rounded-2xl overflow-hidden transition-all duration-300 ease-out"
        style={{
          height:        isOpen ? '520px' : '0px',
          opacity:       isOpen ? 1 : 0,
          pointerEvents: isOpen ? 'auto' : 'none',
          transform:     isOpen ? 'translateY(0) scale(1)' : 'translateY(16px) scale(0.97)',
          boxShadow:     `0 24px 64px ${shadowColor}, 0 4px 16px rgba(15,23,42,0.10)`,
          right:         offsetRight,
        }}
      >
        {children}
      </div>
    </>
  )
}

// ── Main overlay shell ────────────────────────────────────────────────────────
//
// Two independent panels:
//   • Ariel  (teal, right side)   — authenticated users only, via ChatContext.isOpen
//   • Eliya  (indigo, right side) — all users, via ChatContext.isEliyaOpen
//
// Opening one closes the other (enforced in ChatContext).

export function ChatOverlay() {
  const { isOpen, closeChat, isEliyaOpen, closeEliya } = useChat()
  const { user, loading } = useAuth()
  const [mounted, setMounted] = useState(false)

  useEffect(() => { setMounted(true) }, [])
  if (!mounted || loading) return null

  return (
    <>
      {/* Ariel panel — teal Career Agent, authenticated only */}
      {user && (
        <OverlayShell
          isOpen={isOpen}
          onBackdropClick={closeChat}
          ariaLabel="Ask Ariel — Career Agent"
          shadowColor="rgba(13,148,136,0.18)"
        >
          <AuthChatPanel onClose={closeChat} />
        </OverlayShell>
      )}

      {/* Eliya panel — indigo Support, available to all users */}
      <OverlayShell
        isOpen={isEliyaOpen}
        onBackdropClick={closeEliya}
        ariaLabel="Ask Eliya — Support & Onboarding"
        shadowColor="rgba(79,70,229,0.18)"
      >
        <PublicChatPanel onClose={closeEliya} />
      </OverlayShell>
    </>
  )
}
