// Match Feed — job matches with "Why this match" reasoning

function ScoreRing({ score, size = 56 }) {
  const r   = (size - 8) / 2;
  const c   = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const color =
    score >= 85 ? TOKENS.color.success :
    score >= 70 ? TOKENS.color.primary :
    score >= 55 ? TOKENS.color.warn    : TOKENS.color.danger;
  return (
    <div className="relative inline-flex shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={r} stroke="#EEF0F3" strokeWidth="4" fill="none"/>
        <circle cx={size/2} cy={size/2} r={r} stroke={color} strokeWidth="4" fill="none"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)} strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 600ms ease' }}/>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[12px] font-semibold text-slate-900 font-mono tabular-nums leading-none">{typeof score === 'number' ? score.toFixed(1) : score}</span>
        <span className="text-[9px] uppercase tracking-wider text-slate-400 mt-0.5">match</span>
      </div>
    </div>
  );
}

function CompanyLogo({ company }) {
  const hue      = Math.abs([...company].reduce((h, c) => h * 31 + c.charCodeAt(0), 7)) % 360;
  const bg       = `oklch(0.94 0.05 ${hue})`;
  const fg       = `oklch(0.35 0.12 ${hue})`;
  const initials = company.split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();
  return (
    <div
      className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-[13px] font-semibold shrink-0"
      style={{ background: bg, color: fg, border: '1px solid rgba(0,0,0,0.04)' }}
    >
      {initials}
    </div>
  );
}

function ReasonChip({ reason }) {
  const toneMap = {
    skill: { bg: TOKENS.color.successSoft, fg: 'oklch(0.36 0.10 155)', bd: 'oklch(0.85 0.08 155)' },
    exp:   { bg: TOKENS.color.primarySoft, fg: TOKENS.color.primaryInk, bd: 'oklch(0.85 0.07 255)' },
    loc:   { bg: TOKENS.color.violetSoft,  fg: 'oklch(0.38 0.14 295)', bd: 'oklch(0.85 0.07 295)' },
    comp:  { bg: TOKENS.color.warnSoft,    fg: 'oklch(0.40 0.10 80)',  bd: 'oklch(0.85 0.09 80)'  },
    neg:   { bg: TOKENS.color.dangerSoft,  fg: 'oklch(0.42 0.14 25)',  bd: 'oklch(0.87 0.07 25)'  },
  };
  const s = toneMap[reason.kind] || toneMap.skill;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px]"
      style={{ background: s.bg, color: s.fg, border: `1px solid ${s.bd}` }}
    >
      {reason.kind === 'neg' ? <I.x s={10}/> : <I.check s={10}/>}
      {reason.label}
    </span>
  );
}

// Inline bookmark SVG — filled when saved
function BookmarkIcon({ filled, s = 14 }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 3h12v18l-6-4-6 4z"/>
    </svg>
  );
}

// Small badge showing whether a job was manually added or auto-found
function SourceBadge({ source }) {
  const isManual = source === 'manual';
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
      style={isManual
        ? { background: TOKENS.color.violetSoft, color: 'oklch(0.38 0.14 295)', border: '1px solid oklch(0.85 0.07 295)' }
        : { background: TOKENS.color.lineSoft,   color: TOKENS.color.muted,      border: '1px solid oklch(0.90 0.01 255)' }
      }
    >
      {isManual ? <I.pin s={9}/> : <I.spark s={9}/>}
      {isManual ? 'Manual' : 'Auto'}
    </span>
  );
}

// ── Score Breakdown ───────────────────────────────────────────────────────────

const _AXIS_META = {
  CR: { label: 'Contextual Relevance',  weight: '35.2%' },
  TD: { label: 'Technical Depth',       weight: '25.5%' },
  ST: { label: 'Seniority Trajectory',  weight: '19.8%' },
  CD: { label: 'Company DNA',           weight:  '9.5%' },
  ED: { label: 'Evidence Density',      weight: '10.0%' },
};

function _parseRationale(text) {
  if (!text) return null;
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const out = { axes: [], weighted: null, penalties: null, hasPenalties: false, final: null };
  for (const line of lines) {
    if (/^(?:Axes|צירים)\s*[→>]/i.test(line)) {
      for (const m of line.matchAll(/([A-Z]{2})=(\d+)/g)) {
        const key = m[1];
        out.axes.push({ key, label: _AXIS_META[key]?.label || key,
                        weight: _AXIS_META[key]?.weight || '', value: parseInt(m[2], 10) });
      }
    } else if (/^Weighted:/i.test(line)) {
      out.weighted = line.replace(/^Weighted:\s*/i, '').trim();
    } else if (/^Penalties:/i.test(line)) {
      const pen = line.replace(/^Penalties:\s*/i, '').trim();
      out.penalties = pen;
      out.hasPenalties = !/^none$/i.test(pen) && pen !== '' && pen !== '0';
    } else if (/^Final:/i.test(line)) {
      out.final = line.replace(/^Final:\s*/i, '').trim();
    }
  }
  return out;
}

function _axisColor(v) {
  return v >= 75 ? TOKENS.color.success :
         v >= 55 ? TOKENS.color.primary :
         v >= 40 ? TOKENS.color.warn    : TOKENS.color.danger;
}

// Extract only the human-readable reason from a penalty string, stripping
// code tokens like "P1×1=−20.5pts" and their surrounding parentheses.
function _penaltyReason(text) {
  const parens = [...text.matchAll(/\(([^)]+)\)/g)].map(m => m[1].trim());
  if (parens.length > 0) return parens.join(' · ');
  return text.replace(/P\d+[×x]\d+=−[\d.]+pts\s*/gi, '').replace(/[()]/g, '').trim();
}

function ScoreBreakdown({ rationale }) {
  const [open, setOpen] = React.useState(false);
  if (!rationale) return null;

  const parsed = _parseRationale(rationale);
  if (!parsed) return null;

  return (
    <div className="mt-2" onClick={e => e.stopPropagation()}>
      {/* Toggle trigger */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider transition-colors"
        style={{ color: open ? TOKENS.color.primaryInk : TOKENS.color.muted }}
      >
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M2 4h12M4 8h8M6 12h4"/>
        </svg>
        Score Breakdown
        <svg width="9" height="9" viewBox="0 0 10 10" fill="currentColor"
             style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 200ms' }}>
          <path d="M1 3l4 4 4-4"/>
        </svg>
      </button>

      {open && (
        <div
          className="mt-2 rounded-lg border p-3 space-y-3"
          style={{ background: '#FAFBFC', borderColor: TOKENS.color.line }}
        >
          {/* Axes */}
          {parsed.axes.length > 0 && (
            <div className="space-y-1.5">
              {parsed.axes.map(ax => (
                <div key={ax.key} className="flex items-center gap-2">
                  <div className="flex items-baseline gap-1.5 shrink-0" style={{ width: 196 }}>
                    <span className="text-[11.5px] font-medium text-slate-700 leading-none">{ax.label}</span>
                    <span className="text-[10px] font-mono text-slate-400 leading-none">{ax.weight}</span>
                  </div>
                  <div className="flex-1 rounded-full" style={{ height: 4, background: TOKENS.color.lineSoft }}>
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${ax.value}%`, background: _axisColor(ax.value), transition: 'width 500ms ease' }}
                    />
                  </div>
                  <span
                    className="text-[11.5px] font-semibold font-mono tabular-nums shrink-0"
                    style={{ width: 24, textAlign: 'right', color: _axisColor(ax.value) }}
                  >
                    {ax.value}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Penalties */}
          {parsed.penalties && (
            parsed.hasPenalties ? (
              <div
                className="flex items-start gap-2 rounded-md px-2.5 py-2"
                style={{ background: TOKENS.color.dangerSoft, border: `1px solid oklch(0.88 0.07 25)` }}
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="oklch(0.55 0.18 25)"
                     strokeWidth="2" strokeLinecap="round" style={{ marginTop: 1, shrink: 0 }}>
                  <path d="M8 2L1.5 13h13L8 2z"/><line x1="8" y1="7" x2="8" y2="10"/><circle cx="8" cy="12.5" r="0.5" fill="oklch(0.55 0.18 25)" stroke="none"/>
                </svg>
                <div>
                  <div className="text-[10.5px] font-semibold uppercase tracking-wider mb-0.5"
                       style={{ color: 'oklch(0.42 0.14 25)' }}>Knockout Penalty</div>
                  <div className="text-[11px]" style={{ color: 'oklch(0.38 0.16 25)' }}>
                    {_penaltyReason(parsed.penalties)}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-[10.5px]" style={{ color: TOKENS.color.muted }}>
                <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke={TOKENS.color.success}
                     strokeWidth="2" strokeLinecap="round">
                  <path d="M13 4L6 11 3 8"/>
                </svg>
                <span>No penalties</span>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}

function MatchRow({ job, selected, onSelect, onDismiss, onApply, saved, onSave, onReviewCV }) {
  return (
    <div
      onClick={() => onSelect(job.id)}
      className={`group cursor-pointer rounded-xl border transition-all ${
        selected
          ? 'bg-white border-indigo-300'
          : 'bg-white border-slate-200 hover:border-slate-300'
      } ${job.isOpen === false ? 'opacity-60' : ''}`}
      style={
        selected
          ? { boxShadow: '0 0 0 3px oklch(0.95 0.03 255), 0 1px 2px rgba(16,24,40,0.06)' }
          : { boxShadow: TOKENS.shadow.card }
      }
    >
      <div className="p-4 flex gap-4">
        <ScoreRing score={job.score}/>

        <div className="flex-1 min-w-0">
          <div className="flex items-start gap-3">
            <CompanyLogo company={job.company}/>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-[14.5px] font-semibold text-slate-900 truncate">{job.title}</h3>
                {job.isNew  && <Pill tone="primary">New</Pill>}
                {job.remote && <Pill tone="muted">Remote</Pill>}
                {job.isOpen === false && (
                  <span className="text-[10.5px] font-medium px-1.5 py-0.5 rounded-md"
                        style={{ background: TOKENS.color.dangerSoft, color: 'oklch(0.42 0.14 25)' }}>
                    Closed
                  </span>
                )}
                <SourceBadge source={job.source}/>
              </div>
              <div className="flex items-center gap-2 text-[12.5px] text-slate-500 mt-0.5 flex-wrap">
                <span className="font-medium text-slate-700">{job.company}</span>
                <span className="text-slate-300">·</span>
                <span className="inline-flex items-center gap-1"><I.pin s={11}/>{job.location}</span>
                {job.salary && <>
                  <span className="text-slate-300">·</span>
                  <span className="inline-flex items-center gap-1"><I.dollar s={11}/>{job.salary}</span>
                </>}
                <span className="text-slate-300">·</span>
                <span className="inline-flex items-center gap-1 font-mono"><I.clock s={11}/>{job.posted}</span>
              </div>
            </div>
          </div>

          {/* Why this match */}
          <div className="mt-3 rounded-lg bg-slate-50 border border-slate-100 p-2.5">
            <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5">
              <I.spark s={11}/> Why this match
            </div>
            <div className="flex flex-wrap gap-1.5">
              {job.reasons.map((r, i) => <ReasonChip key={i} reason={r}/>)}
            </div>
          </div>

          <ScoreBreakdown rationale={job.scoringRationale}/>
        </div>

        {/* Actions */}
        <div className="flex flex-col items-end gap-2 shrink-0" onClick={e => e.stopPropagation()}>
          <div className="flex items-center gap-1">
            {/* Dismiss */}
            <IconBtn
              title="Dismiss"
              onClick={() => onDismiss(job.id)}
            >
              <I.x s={14}/>
            </IconBtn>

            {/* Save / Bookmark toggle */}
            <IconBtn
              title={saved ? 'Saved' : 'Save'}
              onClick={() => onSave(job.id)}
              className={saved ? 'text-slate-900' : 'text-slate-400'}
            >
              <BookmarkIcon s={14} filled={saved}/>
            </IconBtn>

            {/* Open analysis report */}
            <IconBtn
              title="View full analysis"
              onClick={() => onReviewCV(job.id)}
              className="text-slate-400 hover:text-slate-900"
            >
              <I.file s={14}/>
            </IconBtn>
          </div>

          <Button
            size="sm"
            onClick={() => onApply(job.id)}
            icon={<I.bolt s={12}/>}
          >
            Auto-Apply
          </Button>

          {job.applyUrl && (
            <a
              href={job.applyUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="text-[11.5px] text-slate-500 hover:text-slate-900 inline-flex items-center gap-1"
            >
              View posting <I.ext s={10}/>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function MatchFilters({ filter, setFilter, count, categories, categoryFilter, setCategoryFilter,
                        minScore, setMinScore, sourceFilter, setSourceFilter }) {
  const tabs = [
    { id: 'all',    label: 'All'      },
    { id: 'strong', label: '85+ score'},
    { id: 'new',    label: 'New'      },
    { id: 'remote', label: 'Remote'   },
    { id: 'saved',  label: 'Saved'    },
  ];
  const sourceTabs = [
    { id: 'all',       label: 'All'             },
    { id: 'manual',    label: 'Manual Uploads'  },
    { id: 'automatic', label: 'Auto-Found'      },
  ];
  return (
    <div className="mb-3 space-y-2">
      {/* Row 1: status tabs + result count */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="inline-flex items-center rounded-lg border border-slate-200 bg-white p-0.5">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setFilter(t.id)}
              className={`px-3 h-7 rounded-md text-[12.5px] font-medium transition ${
                filter === t.id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900'
              }`}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {/* Source toggle */}
          <div className="inline-flex items-center rounded-lg border border-slate-200 bg-white p-0.5">
            {sourceTabs.map(t => (
              <button key={t.id} onClick={() => setSourceFilter(t.id)}
                className={`px-2.5 h-7 rounded-md text-[11.5px] font-medium transition ${
                  sourceFilter === t.id ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-800'
                }`}>
                {t.label}
              </button>
            ))}
          </div>
          <span className="text-[12px] text-slate-500 font-mono tabular-nums">{count} results</span>
        </div>
      </div>

      {/* Row 2: category pills (only rendered when categories exist) */}
      {categories.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold mr-1">Category</span>
          {['all', ...categories].map(cat => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              className={`px-2.5 h-6 rounded-full text-[11.5px] font-medium border transition ${
                categoryFilter === cat
                  ? 'bg-slate-900 text-white border-slate-900'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
              }`}
            >
              {cat === 'all' ? 'All categories' : cat}
            </button>
          ))}
        </div>
      )}

      {/* Row 3: minimum score slider */}
      <div className="rounded-lg border border-slate-100 bg-white px-3 py-2.5">
        <Slider
          value={minScore}
          onChange={setMinScore}
          min={0}
          max={100}
          step={1}
          labelLeft="Min match score"
          labelRight={minScore > 0 ? `≥ ${minScore.toFixed(0)}` : 'Any score'}
        />
      </div>
    </div>
  );
}

function MatchFeed({ jobs, selected, setSelected, onDismiss, onApply, savedIds, onSave, onReviewCV,
                     categories, categoryFilter, setCategoryFilter, minScore, setMinScore,
                     sourceFilter, setSourceFilter }) {
  const [filter, setFilter] = React.useState('all');
  const _sourceFilter = sourceFilter || 'all';
  const _setSourceFilter = setSourceFilter || (() => {});

  const filtered = jobs.filter(j => {
    if (filter === 'strong') { if (j.score < 85)              return false; }
    if (filter === 'new')    { if (!j.isNew)                  return false; }
    if (filter === 'remote') { if (!j.remote)                 return false; }
    if (filter === 'saved')  { if (!savedIds.includes(j.id))  return false; }
    if (categoryFilter !== 'all' && j.category !== categoryFilter) return false;
    if (minScore > 0 && j.score < minScore)                   return false;
    if (_sourceFilter !== 'all' && j.source !== _sourceFilter) return false;
    return true;
  });

  return (
    <section>
      <SectionHeader
        title="Match Feed"
        subtitle="Ranked by the Matcher agent — updated continuously"
      />
      <MatchFilters
        filter={filter} setFilter={setFilter} count={filtered.length}
        categories={categories || []}
        categoryFilter={categoryFilter} setCategoryFilter={setCategoryFilter}
        minScore={minScore} setMinScore={setMinScore}
        sourceFilter={_sourceFilter} setSourceFilter={_setSourceFilter}
      />
      <div className="space-y-2.5">
        {filtered.map(j => (
          <MatchRow
            key={j.id}
            job={j}
            selected={selected === j.id}
            onSelect={setSelected}
            onDismiss={onDismiss}
            onApply={onApply}
            saved={savedIds.includes(j.id)}
            onSave={onSave}
            onReviewCV={onReviewCV}
          />
        ))}
        {filtered.length === 0 && (
          <div className="py-10 text-center text-[13px] text-slate-400">
            No matches in this view yet.
          </div>
        )}
      </div>
    </section>
  );
}

window.MatchFeed     = MatchFeed;
window.ScoreRing     = ScoreRing;
window.CompanyLogo   = CompanyLogo;
window.ReasonChip    = ReasonChip;
window.ScoreBreakdown = ScoreBreakdown;
