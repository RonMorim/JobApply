// Design tokens + small shared primitives for Job Apply
// Exposed on window so other Babel scripts can consume.

const TOKENS = {
  color: {
    bg:       '#F7F8FA',
    surface:  '#FFFFFF',
    ink:      '#0B1220',
    ink2:     '#1F2937',
    muted:    '#6B7280',
    line:     '#E5E7EB',
    lineSoft: '#EEF0F3',
    primary:  'oklch(0.55 0.18 255)',
    primaryInk:'oklch(0.42 0.18 255)',
    primarySoft:'oklch(0.96 0.03 255)',
    success:  'oklch(0.68 0.14 155)',
    successSoft:'oklch(0.96 0.04 155)',
    warn:     'oklch(0.78 0.14 80)',
    warnSoft: 'oklch(0.97 0.05 85)',
    danger:   'oklch(0.62 0.18 25)',
    dangerSoft:'oklch(0.97 0.03 25)',
    violet:   'oklch(0.58 0.17 295)',
    violetSoft:'oklch(0.96 0.03 295)',
  },
  radius: { sm: 6, md: 8, lg: 12, xl: 16 },
  shadow: {
    card: '0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)',
    pop:  '0 6px 20px rgba(16,24,40,0.08), 0 2px 6px rgba(16,24,40,0.06)',
  },
};

// Status dot (animated pulse for live states)
function StatusDot({ tone = 'success', pulse = false, size = 8 }) {
  const colors = {
    success: TOKENS.color.success,
    warn:    TOKENS.color.warn,
    danger:  TOKENS.color.danger,
    muted:   '#9CA3AF',
    primary: TOKENS.color.primary,
  };
  const c = colors[tone] || colors.muted;
  return (
    <span className="relative inline-flex" style={{ width: size, height: size }}>
      {pulse && (
        <span
          className="absolute inline-flex h-full w-full rounded-full opacity-60"
          style={{ background: c, animation: 'ja-ping 1.6s cubic-bezier(0,0,.2,1) infinite' }}
        />
      )}
      <span className="relative inline-flex rounded-full" style={{ width: size, height: size, background: c }} />
    </span>
  );
}

function Pill({ children, tone = 'muted', className = '' }) {
  const map = {
    success: { bg: TOKENS.color.successSoft, fg: 'oklch(0.38 0.10 155)', bd: 'oklch(0.86 0.08 155)' },
    warn:    { bg: TOKENS.color.warnSoft,    fg: 'oklch(0.42 0.10 80)',  bd: 'oklch(0.86 0.09 80)' },
    danger:  { bg: TOKENS.color.dangerSoft,  fg: 'oklch(0.42 0.14 25)',  bd: 'oklch(0.88 0.07 25)' },
    primary: { bg: TOKENS.color.primarySoft, fg: TOKENS.color.primaryInk,bd: 'oklch(0.86 0.07 255)' },
    violet:  { bg: TOKENS.color.violetSoft,  fg: 'oklch(0.40 0.14 295)', bd: 'oklch(0.86 0.07 295)' },
    muted:   { bg: '#F3F4F6', fg: '#374151', bd: '#E5E7EB' },
  };
  const s = map[tone] || map.muted;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${className}`}
      style={{ background: s.bg, color: s.fg, border: `1px solid ${s.bd}` }}
    >
      {children}
    </span>
  );
}

function Button({ children, variant = 'primary', size = 'md', icon, className = '', ...rest }) {
  const sizes = {
    sm: 'h-8 px-3 text-[12.5px]',
    md: 'h-9 px-3.5 text-[13px]',
    lg: 'h-10 px-4 text-[14px]',
  };
  const base = 'inline-flex items-center gap-1.5 rounded-md font-medium transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1';
  const variants = {
    primary: 'text-white shadow-sm hover:brightness-110',
    secondary: 'bg-white text-slate-800 border border-slate-200 hover:bg-slate-50',
    ghost:   'bg-transparent text-slate-600 hover:bg-slate-100',
    danger:  'bg-white text-rose-600 border border-rose-200 hover:bg-rose-50',
  };
  const style = variant === 'primary'
    ? { background: TOKENS.color.primary, boxShadow: '0 1px 0 rgba(0,0,0,0.05), inset 0 -1px 0 rgba(0,0,0,0.06)' }
    : {};
  return (
    <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} style={style} {...rest}>
      {icon}
      {children}
    </button>
  );
}

function IconBtn({ children, onClick, title, className = '' }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800 transition ${className}`}
    >
      {children}
    </button>
  );
}

// Tiny icon set (outline, 16px by default)
const I = {
  search:  (p={}) => <svg width={p.s||16} height={p.s||16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>,
  bell:    (p={}) => <svg width={p.s||16} height={p.s||16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M6 8a6 6 0 1 1 12 0c0 4 2 5 2 7H4c0-2 2-3 2-7Z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>,
  settings:(p={}) => <svg width={p.s||16} height={p.s||16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>,
  play:    (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7Z"/></svg>,
  pause:   (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h3v14H7zM14 5h3v14h-3z"/></svg>,
  check:   (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12.5 9 17 20 6"/></svg>,
  x:       (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 6l12 12M18 6l-12 12"/></svg>,
  plus:    (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>,
  arrow:   (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>,
  spark:   (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>,
  filter:  (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 5h16l-6 8v6l-4-2v-4L4 5Z"/></svg>,
  dot:     (p={}) => <svg width={p.s||4} height={p.s||4} viewBox="0 0 4 4"><circle cx="2" cy="2" r="2" fill="currentColor"/></svg>,
  scraper: (p={}) => <svg width={p.s||18} height={p.s||18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7h18M3 12h18M3 17h12"/><circle cx="19" cy="17" r="2.5"/><path d="m21 19 2 2"/></svg>,
  analyzer:(p={}) => <svg width={p.s||18} height={p.s||18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>,
  matcher: (p={}) => <svg width={p.s||18} height={p.s||18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="4"/><circle cx="16" cy="16" r="4"/><path d="m11 11 2 2"/></svg>,
  applier: (p={}) => <svg width={p.s||18} height={p.s||18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h12l4 4v12H4z"/><path d="M8 12h8M8 16h5"/></svg>,
  home:    (p={}) => <svg width={p.s||16} height={p.s||16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m3 11 9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/></svg>,
  briefcase:(p={}) => <svg width={p.s||16} height={p.s||16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>,
  file:    (p={}) => <svg width={p.s||16} height={p.s||16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7 3h8l5 5v13H7z"/><path d="M14 3v6h6"/></svg>,
  chart:   (p={}) => <svg width={p.s||16} height={p.s||16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/></svg>,
  bolt:    (p={}) => <svg width={p.s||14} height={p.s||14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>,
  ext:     (p={}) => <svg width={p.s||12} height={p.s||12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M20 14v6H4V4h6"/></svg>,
  pin:     (p={}) => <svg width={p.s||12} height={p.s||12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 1 8 8c0 5-8 12-8 12S4 15 4 10a8 8 0 0 1 8-8Z"/></svg>,
  clock:   (p={}) => <svg width={p.s||12} height={p.s||12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>,
  dollar:  (p={}) => <svg width={p.s||12} height={p.s||12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v18M17 7H9.5a3 3 0 0 0 0 6h5a3 3 0 1 1 0 6H6"/></svg>,
  building:(p={}) => <svg width={p.s||12} height={p.s||12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 21V5l8-2v18M12 21V9l8 2v10M4 21h16M8 8v0M8 12v0M8 16v0M16 13v0M16 17v0"/></svg>,
};

// Simple SVG logo mark for Job Apply — original geometric mark, not a brand copy.
function Logo({ size = 26 }) {
  return (
    <div className="inline-flex items-center gap-2">
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <rect width="32" height="32" rx="8" fill={TOKENS.color.primary}/>
        <path d="M9 10h14M9 16h10M9 22h7" stroke="white" strokeWidth="2.2" strokeLinecap="round"/>
        <circle cx="23" cy="22" r="3" fill="white"/>
        <path d="m21.5 22 1.3 1.3 2.2-2.6" stroke={TOKENS.color.primary} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
      <span className="font-semibold text-[15px] tracking-tight text-slate-900">Job<span style={{color: TOKENS.color.primary}}>Apply</span></span>
    </div>
  );
}

function SectionHeader({ title, subtitle, right }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-3">
      <div>
        <h2 className="text-[15px] font-semibold text-slate-900 tracking-tight">{title}</h2>
        {subtitle && <p className="text-[12.5px] text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

window.TOKENS        = TOKENS;
window.StatusDot     = StatusDot;
window.Pill          = Pill;
window.Button        = Button;
window.IconBtn       = IconBtn;
window.I             = I;
window.Logo          = Logo;
window.SectionHeader = SectionHeader;
