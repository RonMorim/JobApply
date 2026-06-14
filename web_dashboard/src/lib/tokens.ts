export const TOKENS = {
  color: {
    bg:          '#F8FAFC',   // slate-50 — editorial canvas
    surface:     '#FFFFFF',
    ink:         '#0F172A',   // slate-900
    ink2:        '#334155',   // slate-700
    muted:       '#64748B',   // slate-500
    subtle:      '#94A3B8',   // slate-400
    line:        '#E2E8F0',   // slate-200 — crisp borders
    lineSoft:    '#F1F5F9',   // slate-100
    primary:     '#0D9488',   // teal-600 — deep teal
    primaryHover:'#0F766E',   // teal-700
    primarySoft: '#F0FDFA',   // teal-50
    success:     'oklch(0.65 0.13 155)',
    warn:        'oklch(0.75 0.13 80)',
    danger:      'oklch(0.60 0.17 25)',
    violet:      'oklch(0.52 0.18 290)',
  },
  shadow: {
    card: '0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04)',
  },
}

export type Tone = 'success' | 'warn' | 'danger' | 'muted' | 'primary'
