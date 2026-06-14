'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCrmBoard, moveCrmCard } from '@/lib/api'
import type { CrmBoard, CrmCard, CrmColumn } from '@/lib/apiTypes'
import { TOKENS } from '@/lib/tokens'

// ── Stage visual config ───────────────────────────────────────────────────────

type StageKey = 'submitted' | 'phone screen' | 'technical' | 'interview' | 'offer' | 'rejected'

const STAGE_STYLE: Record<StageKey, { header: string; dot: string; count: string; dropBg: string }> = {
  'submitted':    { header: 'bg-teal-50   border-teal-200',   dot: 'bg-teal-500',    count: 'bg-teal-100   text-teal-700',   dropBg: 'bg-teal-100   border-teal-400'   },
  'phone screen': { header: 'bg-sky-50    border-sky-200',    dot: 'bg-sky-400',     count: 'bg-sky-100    text-sky-700',    dropBg: 'bg-sky-100    border-sky-400'    },
  'technical':    { header: 'bg-violet-50 border-violet-200', dot: 'bg-violet-500',  count: 'bg-violet-100 text-violet-700', dropBg: 'bg-violet-100 border-violet-400' },
  'interview':    { header: 'bg-amber-50  border-amber-200',  dot: 'bg-amber-500',   count: 'bg-amber-100  text-amber-700',  dropBg: 'bg-amber-100  border-amber-400'  },
  'offer':        { header: 'bg-emerald-50 border-emerald-200', dot: 'bg-emerald-500', count: 'bg-emerald-100 text-emerald-700', dropBg: 'bg-emerald-100 border-emerald-400' },
  'rejected':     { header: 'bg-rose-50   border-rose-200',   dot: 'bg-rose-400',    count: 'bg-rose-100   text-rose-700',   dropBg: 'bg-rose-100   border-rose-400'   },
}

function stageStyle(stage: string) {
  return STAGE_STYLE[stage as StageKey] ?? {
    header: 'bg-slate-50 border-slate-200',
    dot:    'bg-slate-400',
    count:  'bg-slate-100 text-slate-600',
    dropBg: 'bg-slate-200 border-slate-400',
  }
}

const ALL_STAGES: { key: StageKey; label: string }[] = [
  { key: 'submitted',    label: 'Submitted'    },
  { key: 'phone screen', label: 'Phone Screen' },
  { key: 'technical',    label: 'Technical'    },
  { key: 'interview',    label: 'Interview'    },
  { key: 'offer',        label: 'Offer'        },
  { key: 'rejected',     label: 'Rejected'     },
]

// ── Date formatter ─────────────────────────────────────────────────────────────
// Converts "2026-05-27 09:17 UTC" → "May 27, 09:17"

function formatCardDate(raw: string): string {
  if (!raw) return ''
  try {
    // Normalise "2026-05-27 09:17 UTC" → ISO by replacing space with T and removing " UTC"
    const iso = raw.replace(' UTC', 'Z').replace(' ', 'T')
    const d   = new Date(iso)
    if (isNaN(d.getTime())) return raw
    const month = d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' })
    const day   = d.getUTCDate()
    const hh    = String(d.getUTCHours()).padStart(2, '0')
    const mm    = String(d.getUTCMinutes()).padStart(2, '0')
    return `${month} ${day}, ${hh}:${mm}`
  } catch {
    return raw
  }
}

// ── Card Detail Modal ──────────────────────────────────────────────────────────

interface CardModalProps {
  card:         CrmCard
  currentStage: string
  onClose:      () => void
  onMove:       (toStage: string) => void
  moving:       boolean
}

function CardDetailModal({ card, currentStage, onClose, onMove, moving }: CardModalProps) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const s = stageStyle(currentStage)

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          className="w-full max-w-md rounded-2xl bg-white shadow-2xl pointer-events-auto flex flex-col"
          style={{ boxShadow: '0 24px 64px rgba(15,23,42,0.22)' }}
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between px-5 pt-5 pb-4 border-b border-slate-100">
            <div className="min-w-0 flex-1 pr-3">
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
                {card.company}
              </p>
              <h3 className="text-[15px] font-bold text-slate-900 leading-snug">
                {card.title}
              </h3>
              <div className="flex items-center gap-2 mt-2">
                {/* Current stage badge */}
                <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full ${
                  stageStyle(currentStage).count
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                  {ALL_STAGES.find(s => s.key === currentStage)?.label ?? currentStage}
                </span>
                {card.score > 0 && (
                  <span className="text-[11px] text-slate-400 font-medium">
                    {Math.round(card.score)}% ATS
                  </span>
                )}
              </div>
              {card.last_update && (
                <p className="text-[11px] text-slate-400 mt-1.5">
                  Updated: {formatCardDate(card.last_update)}
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition"
            >
              <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Stage action buttons */}
          <div className="px-5 py-4">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Move to stage
            </p>
            <div className="grid grid-cols-3 gap-2">
              {ALL_STAGES.map(({ key, label }) => {
                const isCurrent = key === currentStage
                const s2        = stageStyle(key)
                return (
                  <button
                    key={key}
                    onClick={() => !isCurrent && onMove(key)}
                    disabled={moving || isCurrent}
                    className={`
                      flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-[11.5px] font-medium
                      transition-all duration-100 border
                      ${isCurrent
                        ? `${s2.count} border-transparent cursor-default ring-2 ring-offset-1 ring-current/30`
                        : `bg-white text-slate-600 border-slate-200 hover:${s2.count} hover:border-transparent`
                      }
                      disabled:opacity-50
                    `}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s2.dot}`} />
                    {label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Footer */}
          <div className="px-5 pb-5 pt-1 flex justify-end">
            <button
              onClick={onClose}
              className="h-8 px-4 rounded-lg text-[12.5px] font-medium text-slate-600 border border-slate-200 hover:bg-slate-50 transition"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

// ── Card ──────────────────────────────────────────────────────────────────────

function KanbanCard({
  card,
  onDragStart,
  isMoving,
  onOpen,
}: {
  card:        CrmCard
  onDragStart: (card: CrmCard) => void
  isMoving:    boolean
  onOpen:      (card: CrmCard) => void
}) {
  return (
    <div
      draggable
      onDragStart={e => { e.stopPropagation(); onDragStart(card) }}
      onClick={() => onOpen(card)}
      className={`
        group bg-white rounded-2xl border border-slate-100
        hover:border-slate-200 hover:shadow-md
        transition-all duration-150 cursor-pointer active:cursor-grabbing
        select-none p-3.5
        ${isMoving ? 'opacity-40 scale-95' : ''}
      `}
    >
      {/* Title + drag hint */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <p className="text-[12px] font-semibold text-slate-900 leading-snug line-clamp-2 flex-1">
          {card.title}
        </p>
        <svg
          className="shrink-0 mt-0.5 text-slate-300 group-hover:text-slate-400 transition-colors"
          width={10} height={14} viewBox="0 0 10 14" fill="currentColor"
        >
          <circle cx="2.5" cy="2.5"  r="1.5" />
          <circle cx="7.5" cy="2.5"  r="1.5" />
          <circle cx="2.5" cy="7"    r="1.5" />
          <circle cx="7.5" cy="7"    r="1.5" />
          <circle cx="2.5" cy="11.5" r="1.5" />
          <circle cx="7.5" cy="11.5" r="1.5" />
        </svg>
      </div>

      <p className="text-[11px] font-medium text-slate-500 mb-2 truncate">
        {card.company}
      </p>

      <div className="flex items-center justify-between">
        <span className="text-[10px] text-slate-400 truncate max-w-[70%]">
          {formatCardDate(card.last_update)}
        </span>
        {card.score > 0 && (
          <span className="text-[10px] font-semibold text-slate-500 shrink-0">
            {Math.round(card.score)}%
          </span>
        )}
      </div>
    </div>
  )
}

// ── Column ────────────────────────────────────────────────────────────────────

function KanbanColumn({
  col,
  movingId,
  onDragStart,
  onDrop,
  onOpenCard,
}: {
  col:         CrmColumn
  movingId:    string | null
  onDragStart: (card: CrmCard) => void
  onDrop:      (targetStage: string) => void
  onOpenCard:  (card: CrmCard, stage: string) => void
}) {
  const [isDragOver, setIsDragOver] = useState(false)
  const s = stageStyle(col.stage)

  return (
    <div
      className="flex flex-col min-w-[200px] flex-1 max-w-[240px]"
      onDragOver={e => { e.preventDefault(); setIsDragOver(true) }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={() => { setIsDragOver(false); onDrop(col.stage) }}
    >
      {/* Column header */}
      <div className={`
        flex items-center gap-2 px-3 py-2.5 rounded-t-xl border-x border-t
        ${s.header}
      `}>
        <span className={`w-2 h-2 rounded-full shrink-0 ${s.dot}`} />
        <span className="text-[12px] font-semibold text-slate-700 flex-1">{col.label}</span>
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${s.count}`}>
          {col.cards.length}
        </span>
      </div>

      {/* Cards container */}
      <div
        className={`
          flex-1 min-h-[400px] rounded-b-xl border border-t-0
          transition-all duration-150
          flex flex-col gap-2 p-2
          ${isDragOver
            ? `${s.dropBg} border-dashed`
            : 'bg-slate-50 border-slate-200'
          }
        `}
      >
        {col.cards.length === 0 && !isDragOver && (
          <p className="text-[11px] text-slate-400 italic text-center pt-8 px-2">
            No applications here
          </p>
        )}
        {col.cards.map(card => (
          <KanbanCard
            key={card.application_id}
            card={card}
            onDragStart={onDragStart}
            isMoving={movingId === card.application_id}
            onOpen={c => onOpenCard(c, col.stage)}
          />
        ))}
        {isDragOver && (
          <div className={`
            h-14 rounded-lg border-2 border-dashed flex items-center justify-center
            ${s.dropBg} border-current
          `}>
            <span className="text-[11px] font-medium text-slate-600">Drop here</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function ApplicationsKanban({ onRefresh }: { onRefresh?: () => void }) {
  const [board,    setBoard]    = useState<CrmBoard | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [movingId, setMovingId] = useState<string | null>(null)
  const [toast,    setToast]    = useState<string | null>(null)

  // Modal state
  const [modalCard,  setModalCard]  = useState<CrmCard | null>(null)
  const [modalStage, setModalStage] = useState<string>('')
  const [modalMoving, setModalMoving] = useState(false)

  const draggedCard = useRef<CrmCard | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await fetchCrmBoard()
      setBoard(data)
      setError(null)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 2500)
    return () => clearTimeout(t)
  }, [toast])

  const handleDragStart = useCallback((card: CrmCard) => {
    draggedCard.current = card
  }, [])

  const doMove = useCallback(async (card: CrmCard, targetStage: string) => {
    if (!board || targetStage === card.application_id) return

    // Optimistic update
    setBoard(prev => {
      if (!prev) return prev
      return {
        columns: prev.columns.map(col => ({
          ...col,
          cards: col.stage === targetStage
            ? [...col.cards.filter(c => c.application_id !== card.application_id), { ...card }]
            : col.cards.filter(c => c.application_id !== card.application_id),
        })),
      }
    })

    setMovingId(card.application_id)
    try {
      await moveCrmCard(card.application_id, targetStage)
      const label = ALL_STAGES.find(s => s.key === targetStage)?.label ?? targetStage
      setToast(`Moved to ${label}`)
      onRefresh?.()
    } catch {
      setToast('Move failed — reloading…')
      await load()
    } finally {
      setMovingId(null)
    }
  }, [board, load, onRefresh])

  const handleDrop = useCallback(async (targetStage: string) => {
    const card = draggedCard.current
    draggedCard.current = null
    if (!card) return
    await doMove(card, targetStage)
  }, [doMove])

  const handleOpenCard = useCallback((card: CrmCard, stage: string) => {
    setModalCard(card)
    setModalStage(stage)
  }, [])

  const handleModalMove = useCallback(async (toStage: string) => {
    if (!modalCard) return
    setModalMoving(true)
    // Update the modal's current stage immediately for visual feedback
    const prevStage = modalStage
    setModalStage(toStage)
    try {
      await doMove(modalCard, toStage)
    } catch {
      setModalStage(prevStage)
    } finally {
      setModalMoving(false)
    }
  }, [modalCard, modalStage, doMove])

  // ── States ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-slate-400">
        Loading board…
      </div>
    )
  }

  if (error || !board) {
    return (
      <div className="flex items-center justify-center h-64 text-sm" style={{ color: TOKENS.color.danger }}>
        Failed to load board. {error}
      </div>
    )
  }

  const totalCards = board.columns.reduce((n, c) => n + c.cards.length, 0)

  return (
    <div className="relative">
      {/* Refresh button */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-[12px] text-slate-500">
          {totalCards} application{totalCards !== 1 ? 's' : ''} in pipeline
          <span className="ml-2 text-slate-400">· drag cards between columns or click to update status</span>
        </p>
        <button
          onClick={load}
          className="text-[12px] text-slate-500 hover:text-slate-800 transition flex items-center gap-1.5"
        >
          <svg width={12} height={12} viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Board */}
      <div className="flex gap-3 overflow-x-auto pb-4">
        {board.columns.map(col => (
          <KanbanColumn
            key={col.stage}
            col={col}
            movingId={movingId}
            onDragStart={handleDragStart}
            onDrop={handleDrop}
            onOpenCard={handleOpenCard}
          />
        ))}
      </div>

      {/* Card detail modal */}
      {modalCard && (
        <CardDetailModal
          card={modalCard}
          currentStage={modalStage}
          onClose={() => setModalCard(null)}
          onMove={handleModalMove}
          moving={modalMoving}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-xl shadow-lg text-[13px] font-medium text-white"
          style={{ background: TOKENS.color.success }}>
          {toast}
        </div>
      )}
    </div>
  )
}
