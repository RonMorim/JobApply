'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { TOKENS } from '@/lib/tokens'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CvData {
  title:        string
  summary:      string
  experience:   Array<{
    role:     string
    company:  string
    dates:    string
    bullets:  string[]
  }>
  education:    Array<{
    degree:      string
    institution: string
    dates:       string
    honors:      string
    coursework:  string
  }>
  military?:    { role: string; unit: string; dates: string }
  skills:       { categories: Array<{ label: string; items: string[] }> }
  languages:    Array<{ language: string; level: string }>
  volunteering: string
  [key: string]: unknown
}

export interface LiveEditorProps {
  cvData:           CvData
  originalCvData:   CvData
  onChange:         (updated: CvData) => void
  onReset:          () => void
  isDirty:          boolean
  isSaving:         boolean
  onSave:           () => void
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function UndoIcon() {
  return (
    <svg width={13} height={13} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 14 4 9 9 4" /><path d="M20 20v-7a4 4 0 0 0-4-4H4" />
    </svg>
  )
}

function SaveIcon() {
  return (
    <svg width={13} height={13} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
      <polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" />
    </svg>
  )
}

// ── Small text field (auto-expanding textarea) ────────────────────────────────

function EditableField({
  value, onChange, rows = 2, mono = false, highlight = false,
}: {
  value:     string
  onChange:  (v: string) => void
  rows?:     number
  mono?:     boolean
  highlight?:boolean
}) {
  const ref = useRef<HTMLTextAreaElement>(null)

  // Auto-resize
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  return (
    <textarea
      ref={ref}
      value={value}
      rows={rows}
      dir="auto"
      onChange={e => onChange(e.target.value)}
      style={{
        width: '100%',
        resize: 'none',
        overflow: 'hidden',
        border: `1px solid ${highlight ? 'oklch(0.75 0.14 80)' : TOKENS.color.line}`,
        borderRadius: 6,
        padding: '5px 8px',
        fontSize: mono ? 11 : 11.5,
        fontFamily: mono ? '"SF Mono", "Fira Mono", monospace' : 'inherit',
        lineHeight: 1.5,
        color: TOKENS.color.ink2,
        background: highlight ? 'oklch(0.98 0.02 80)' : TOKENS.color.bg,
        outline: 'none',
        transition: 'border-color 0.15s, background 0.15s',
        textAlign: 'start',
        unicodeBidi: 'plaintext',
      }}
      onFocus={e => { e.currentTarget.style.borderColor = TOKENS.color.primary }}
      onBlur={e => { e.currentTarget.style.borderColor = highlight ? 'oklch(0.75 0.14 80)' : TOKENS.color.line }}
    />
  )
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <p style={{
        fontSize: 9.5, fontWeight: 700, letterSpacing: '1.4px',
        textTransform: 'uppercase', color: TOKENS.color.primary,
        paddingBottom: 4, borderBottom: `0.75px solid ${TOKENS.color.line}`,
        marginBottom: 10,
      }}>
        {title}
      </p>
      {children}
    </div>
  )
}

// ── Skill tag editor ──────────────────────────────────────────────────────────

function SkillCategoryEditor({
  label, items, onChange,
}: { label: string; items: string[]; onChange: (items: string[]) => void }) {
  const [inputVal, setInputVal] = useState('')

  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i))

  const add = () => {
    const v = inputVal.trim()
    if (v && !items.includes(v)) onChange([...items, v])
    setInputVal('')
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <p style={{ fontSize: 10, fontWeight: 600, color: TOKENS.color.muted,
        textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 5 }}>
        {label}
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 5px', marginBottom: 6 }}>
        {items.map((item, i) => (
          <span key={i} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            fontSize: 10.5, fontWeight: 500,
            padding: '2px 7px', borderRadius: 5,
            background: TOKENS.color.primarySoft,
            color: TOKENS.color.primary,
            border: `0.75px solid oklch(0.85 0.06 255)`,
          }}>
            {item}
            <button onClick={() => remove(i)} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: 0, lineHeight: 1, color: TOKENS.color.primary, opacity: 0.6,
              fontSize: 12, marginTop: -1,
            }}>×</button>
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 5 }}>
        <input
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
          placeholder="Add skill…"
          dir="auto"
          style={{
            flex: 1, fontSize: 11, padding: '3px 8px', borderRadius: 5,
            border: `1px solid ${TOKENS.color.line}`,
            background: TOKENS.color.bg, color: TOKENS.color.ink2,
            outline: 'none',
            textAlign: 'start',
            unicodeBidi: 'plaintext',
          }}
        />
        <button onClick={add} style={{
          fontSize: 11, padding: '3px 10px', borderRadius: 5,
          background: TOKENS.color.primarySoft, color: TOKENS.color.primary,
          border: `1px solid oklch(0.85 0.06 255)`, cursor: 'pointer', fontWeight: 600,
        }}>
          +
        </button>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function LiveEditor({
  cvData, originalCvData, onChange, onReset, isDirty, isSaving, onSave,
}: LiveEditorProps) {

  // ── Deep-update helpers ───────────────────────────────────────────────────

  const setSummary = useCallback((v: string) => {
    onChange({ ...cvData, summary: v })
  }, [cvData, onChange])

  const setBullet = useCallback((expIdx: number, bulletIdx: number, v: string) => {
    const experience = cvData.experience.map((exp, ei) =>
      ei === expIdx
        ? { ...exp, bullets: exp.bullets.map((b, bi) => bi === bulletIdx ? v : b) }
        : exp
    )
    onChange({ ...cvData, experience })
  }, [cvData, onChange])

  const setSkillItems = useCallback((catIdx: number, items: string[]) => {
    const categories = (cvData.skills?.categories ?? []).map((cat, ci) =>
      ci === catIdx ? { ...cat, items } : cat
    )
    onChange({ ...cvData, skills: { categories } })
  }, [cvData, onChange])

  // ── Auto-save: debounced 30s after last change ────────────────────────────
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!isDirty) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(onSave, 30_000)
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current) }
  }, [cvData, isDirty, onSave])

  return (
    <div style={{
      width: '100%', height: '100%',
      overflowY: 'auto',
      padding: '16px 20px 20px',
      display: 'flex', flexDirection: 'column',
      gap: 0,
    }}>

      {/* ── Toolbar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 16, flexShrink: 0,
      }}>
        <p style={{ fontSize: 12.5, fontWeight: 600, color: TOKENS.color.ink }}>
          Live Editor
          {isDirty && (
            <span style={{ fontSize: 10.5, fontWeight: 400, color: TOKENS.color.muted, marginLeft: 6 }}>
              · unsaved changes
            </span>
          )}
        </p>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={onReset}
            title="Reset to original generated CV"
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 10px', borderRadius: 20,
              fontSize: 11.5, fontWeight: 500,
              color: TOKENS.color.muted,
              background: 'white',
              border: `1.5px solid ${TOKENS.color.line}`,
              cursor: 'pointer',
            }}
          >
            <UndoIcon /> Reset
          </button>
          <button
            onClick={onSave}
            disabled={!isDirty || isSaving}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 12px', borderRadius: 20,
              fontSize: 11.5, fontWeight: 600,
              color: 'white',
              background: isDirty && !isSaving ? TOKENS.color.primary : TOKENS.color.subtle,
              border: 'none', cursor: isDirty && !isSaving ? 'pointer' : 'default',
              transition: 'background 0.15s',
            }}
          >
            <SaveIcon /> {isSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {/* ── Summary ── */}
      <Section title="Professional Summary">
        <EditableField
          value={cvData.summary}
          onChange={setSummary}
          rows={4}
          highlight={cvData.summary !== originalCvData.summary}
        />
      </Section>

      {/* ── Experience bullets ── */}
      <Section title="Experience">
        {cvData.experience.map((exp, ei) => (
          <div key={ei} style={{ marginBottom: 14 }}>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
              marginBottom: 6,
            }}>
              <p style={{ fontSize: 11.5, fontWeight: 700, color: TOKENS.color.ink }}>
                {exp.role}
              </p>
              <p style={{ fontSize: 10.5, color: TOKENS.color.muted, fontStyle: 'italic' }}>
                {exp.company} · {exp.dates}
              </p>
            </div>
            {exp.bullets.map((bullet, bi) => (
              <div key={bi} style={{ display: 'flex', gap: 6, marginBottom: 5, alignItems: 'flex-start' }}>
                <span style={{
                  marginTop: 7, flexShrink: 0, width: 5, height: 5, borderRadius: '50%',
                  background: TOKENS.color.subtle,
                }} />
                <div style={{ flex: 1 }}>
                  <EditableField
                    value={bullet}
                    onChange={v => setBullet(ei, bi, v)}
                    rows={2}
                    highlight={bullet !== (originalCvData.experience[ei]?.bullets[bi] ?? '')}
                  />
                </div>
              </div>
            ))}
          </div>
        ))}
      </Section>

      {/* ── Military Service (read-only — always injected from verified profile) ── */}
      {cvData.military?.role && (
        <Section title="Military Service">
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
            padding: '7px 10px',
            borderRadius: 7,
            border: `1px solid ${TOKENS.color.line}`,
            background: 'oklch(0.98 0 0)',
          }}>
            <div>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: TOKENS.color.ink }}>
                {cvData.military.role}
              </span>
              <span style={{
                fontSize: 11, color: TOKENS.color.muted,
                fontStyle: 'italic', marginLeft: 6,
              }}>
                {cvData.military.unit}
              </span>
            </div>
            <span style={{ fontSize: 10.5, color: TOKENS.color.muted }}>
              {cvData.military.dates}
            </span>
          </div>
          <p style={{
            fontSize: 10, color: TOKENS.color.muted,
            marginTop: 5, fontStyle: 'italic',
          }}>
            Auto-injected from your verified profile — not editable here.
          </p>
        </Section>
      )}

      {/* ── Volunteering — hidden entirely when absent or empty ── */}
      {cvData.volunteering && cvData.volunteering.trim().length > 0 && (
        <Section title="Volunteering">
          <EditableField
            value={cvData.volunteering}
            onChange={v => onChange({ ...cvData, volunteering: v })}
            rows={2}
            highlight={cvData.volunteering !== originalCvData.volunteering}
          />
        </Section>
      )}

      {/* ── Skills ── */}
      <Section title="Skills">
        {(cvData.skills?.categories ?? []).map((cat, ci) => (
          <SkillCategoryEditor
            key={ci}
            label={cat.label}
            items={cat.items}
            onChange={items => setSkillItems(ci, items)}
          />
        ))}
      </Section>

    </div>
  )
}
