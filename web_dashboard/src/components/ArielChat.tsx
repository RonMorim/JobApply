'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { TOKENS }           from '@/lib/tokens'
import { getAuthHeaders }   from '@/lib/api'
import { useOnboarding }    from '@/contexts/OnboardingContext'

// ── Career stage display labels ───────────────────────────────────────────────
const STAGE_LABELS: Record<string, string> = {
  student:    'Student',
  junior:     'Junior',
  mid:        'Mid-Level',
  senior:     'Senior',
  management: 'Management',
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function sanitize(raw: string): string {
  return raw
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*\s][^*\n]*[^*\s]|[^*\s])\*/g, '$1')
    .replace(/_([^_\s][^_\n]*[^_\s]|[^_\s])_/g, '$1')
    .replace(/—/g, ' - ')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\*\s+/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function SpinnerIcon({ s = 16 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" style={{ animation: 'spin 0.8s linear infinite', flexShrink: 0 }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

function SendIcon({ s = 16 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

// ── ArielChat ─────────────────────────────────────────────────────────────────

export function ArielChat() {
  const { data: onboardingData, clear: clearOnboarding } = useOnboarding()

  const [messages,  setMessages]  = useState<ChatMessage[]>([])
  const [input,     setInput]     = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef  = useRef<HTMLDivElement>(null)
  const textRef    = useRef<HTMLTextAreaElement>(null)
  const abortRef   = useRef<AbortController | null>(null)
  // Guard so the greeting is injected only once per mount
  const greetedRef = useRef(false)

  // ── Inject personalised Ariel greeting on first mount ─────────────────────
  useEffect(() => {
    if (greetedRef.current || !onboardingData) return
    greetedRef.current = true

    const firstName   = onboardingData.fullName.split(' ')[0]
    const stageLabel  = STAGE_LABELS[onboardingData.careerStage] ?? onboardingData.careerStage

    const greeting =
      `Hi ${firstName}! It's great to have you on board. ` +
      `I see you're currently at the ${stageLabel} stage of your career. ` +
      `Let's start building your Master Profile. ` +
      `What is the first thing you'd like to work on?`

    setMessages([{ role: 'assistant', content: greeting }])

    // Consume context so repeat visits don't re-fire the welcome
    clearOnboarding()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')

    const history = messages.map(m => ({ role: m.role, content: m.content }))
    const userMsg: ChatMessage = { role: 'user', content: text }

    setMessages(prev => [...prev, userMsg])
    setStreaming(true)

    // Placeholder for the streaming assistant reply
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch('/api/chat/private', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body:    JSON.stringify({ message: text, chat_history: history }),
        signal:  controller.signal,
      })

      if (!res.ok || !res.body) {
        const errText = await res.text().catch(() => res.statusText)
        throw new Error(errText)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE lines
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (!payload || payload === '[DONE]') continue
          try {
            const parsed = JSON.parse(payload) as { chunk?: string }
            if (parsed.chunk) {
              setMessages(prev => {
                const next = [...prev]
                const last = next[next.length - 1]
                if (last?.role === 'assistant') {
                  next[next.length - 1] = { ...last, content: last.content + parsed.chunk }
                }
                return next
              })
            }
          } catch {
            // ignore malformed SSE line
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      const errMsg = err instanceof Error ? err.message : 'Something went wrong. Please try again.'
      setMessages(prev => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last?.role === 'assistant' && last.content === '') {
          next[next.length - 1] = { role: 'assistant', content: errMsg }
        } else {
          next.push({ role: 'assistant', content: errMsg })
        }
        return next
      })
    } finally {
      setStreaming(false)
      textRef.current?.focus()
    }
  }, [input, messages, streaming])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // Send a message without going through controlled input state
  const quickSend = useCallback(async (text: string) => {
    if (streaming) return
    setStreaming(true)
    const userMsg: ChatMessage = { role: 'user', content: text }
    setMessages([userMsg, { role: 'assistant', content: '' }])

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch('/api/chat/private', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body:    JSON.stringify({ message: text, chat_history: [] }),
        signal:  controller.signal,
      })
      if (!res.ok || !res.body) throw new Error(await res.text().catch(() => res.statusText))

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (!payload || payload === '[DONE]') continue
          try {
            const parsed = JSON.parse(payload) as { chunk?: string }
            if (parsed.chunk) {
              setMessages(prev => {
                const next = [...prev]
                const last = next[next.length - 1]
                if (last?.role === 'assistant') next[next.length - 1] = { ...last, content: last.content + parsed.chunk }
                return next
              })
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      const msg = err instanceof Error ? err.message : 'Something went wrong.'
      setMessages(prev => { const n = [...prev]; n[n.length - 1] = { role: 'assistant', content: msg }; return n })
    } finally {
      setStreaming(false)
      textRef.current?.focus()
    }
  }, [streaming])

  // ── Welcome screen ───────────────────────────────────────────────────────────
  if (messages.length === 0) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 flex flex-col items-center justify-center px-6 gap-6">
          <div className="text-center max-w-md">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center text-white text-2xl font-bold mx-auto mb-4"
              style={{ background: TOKENS.color.primary }}
            >
              A
            </div>
            <h2 className="text-[20px] font-bold text-slate-900 mb-2">Meet Ariel</h2>
            <p className="text-[13.5px] text-slate-500 leading-relaxed">
              Your personal career strategist. I'll help you build a complete Master Profile
              and tailor your CV for every opportunity — starting right now.
            </p>
            <div className="mt-5 grid grid-cols-3 gap-3 text-center">
              {[
                { icon: '🗂️', label: 'Master Profile',  sub: 'One profile for all applications' },
                { icon: '🎯', label: 'Smart Tailoring',  sub: 'Every CV matched to the JD' },
                { icon: '📊', label: 'Gap Analysis',     sub: 'Know where you stand instantly' },
              ].map(f => (
                <div key={f.label} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
                  <div className="text-xl mb-1">{f.icon}</div>
                  <p className="text-[11.5px] font-semibold text-slate-700">{f.label}</p>
                  <p className="text-[10.5px] text-slate-400 mt-0.5">{f.sub}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Suggested openers */}
          <div className="w-full max-w-md space-y-2">
            {[
              "Let's build my Master Profile from scratch.",
              "I have my CV ready — let's start there.",
              "What information do you need from me?",
            ].map(suggestion => (
              <button
                key={suggestion}
                onClick={() => quickSend(suggestion)}
                className="w-full text-left text-[13px] text-slate-600 border border-slate-200 rounded-xl px-4 py-2.5 hover:border-teal-300 hover:bg-teal-50 transition"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>

        {/* Input always visible */}
        <div className="p-3 border-t border-slate-100">
          <div className="flex items-end gap-2">
            <textarea
              ref={textRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Say anything to get started… (Enter to send)"
              rows={2}
              className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-[13px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || streaming}
              className="w-9 h-9 rounded-xl flex items-center justify-center text-white transition disabled:opacity-40 flex-shrink-0"
              style={{ background: TOKENS.color.primary }}
            >
              <SendIcon s={15} />
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Active chat ──────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-100 bg-white flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-full text-white text-[11px] font-bold flex items-center justify-center flex-shrink-0"
            style={{ background: TOKENS.color.primary }}
          >
            A
          </div>
          <p className="text-[13px] font-semibold text-slate-700">Ariel</p>
          <span className="h-5 px-2 rounded-full text-[10px] font-semibold border"
            style={{ background: TOKENS.color.primarySoft, borderColor: '#99f6e4', color: TOKENS.color.primary }}>
            Career Strategist
          </span>
        </div>
        <button
          onClick={() => setMessages([])}
          className="h-7 px-3 rounded-full text-[11.5px] text-slate-400 hover:text-rose-600 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition"
        >
          ↺ New conversation
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div
                className="w-7 h-7 rounded-full text-white text-[11px] font-bold flex items-center justify-center mr-2 mt-0.5 flex-shrink-0"
                style={{ background: TOKENS.color.primary }}
              >
                A
              </div>
            )}
            <div
              className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'text-white rounded-tr-sm'
                  : 'bg-white border border-slate-100 text-slate-800 rounded-tl-sm'
              }`}
              style={msg.role === 'user' ? { background: TOKENS.color.primary } : undefined}
            >
              {msg.role === 'assistant'
                ? (msg.content
                    ? sanitize(msg.content)
                    : <span className="flex items-center gap-2 text-slate-400"><SpinnerIcon s={14} /> Thinking…</span>
                  )
                : msg.content
              }
            </div>
          </div>
        ))}

        {/* Typing indicator while streaming the first token */}
        {streaming && messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1].content === '' && (
          <div className="flex justify-start">
            <div
              className="w-7 h-7 rounded-full text-white text-[11px] font-bold flex items-center justify-center mr-2 mt-0.5 flex-shrink-0"
              style={{ background: TOKENS.color.primary }}
            >
              A
            </div>
            <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-slate-300"
                  style={{ animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite` }}
                />
              ))}
              <style>{`@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}`}</style>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-slate-100">
        <div className="flex items-end gap-2">
          <textarea
            ref={textRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your reply… (Shift+Enter for new line)"
            rows={2}
            className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-[13px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || streaming}
            className="w-9 h-9 rounded-xl flex items-center justify-center text-white transition disabled:opacity-40 flex-shrink-0"
            style={{ background: TOKENS.color.primary }}
          >
            {streaming ? <SpinnerIcon s={15} /> : <SendIcon s={15} />}
          </button>
        </div>
      </div>
    </div>
  )
}
