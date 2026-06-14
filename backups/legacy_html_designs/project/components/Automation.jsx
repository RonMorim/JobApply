// Automation Controls — auto-apply, daily limits, thresholds

function Toggle({ on, onChange, size = 'md' }) {
  const w = size === 'sm' ? 32 : 40;
  const h = size === 'sm' ? 18 : 22;
  const d = h - 4;
  return (
    <button onClick={() => onChange(!on)}
      className="inline-flex items-center rounded-full transition-colors"
      style={{ width: w, height: h, background: on ? TOKENS.color.primary : '#E5E7EB', padding: 2 }}>
      <span className="rounded-full bg-white shadow transition-transform"
        style={{ width: d, height: d, transform: `translateX(${on ? w - d - 4 : 0}px)` }}/>
    </button>
  );
}

function Slider({ value, onChange, min = 0, max = 50, step = 1, labelLeft, labelRight }) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <div className="flex items-center justify-between text-[11.5px] text-slate-500 mb-1.5">
        <span>{labelLeft}</span>
        <span className="font-mono text-slate-900 tabular-nums">{labelRight}</span>
      </div>
      <div className="relative h-6 flex items-center">
        <div className="absolute inset-x-0 h-1.5 rounded-full bg-slate-200"/>
        <div className="absolute h-1.5 rounded-full" style={{ width: `${pct}%`, background: TOKENS.color.primary }}/>
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="absolute inset-0 w-full opacity-0 cursor-pointer"/>
        <div className="absolute h-4 w-4 rounded-full bg-white border-2 pointer-events-none"
          style={{ left: `calc(${pct}% - 8px)`, borderColor: TOKENS.color.primary, boxShadow: '0 1px 3px rgba(0,0,0,.15)' }}/>
      </div>
    </div>
  );
}

function Row({ title, sub, control }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-slate-100 last:border-0">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-slate-900">{title}</div>
        {sub && <div className="text-[11.5px] text-slate-500 mt-0.5 leading-snug">{sub}</div>}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}

function AutomationControls({ settings, setSettings }) {
  const s = settings;
  const set = (patch) => setSettings({ ...s, ...patch });
  const dailyPct = Math.round((s.dailyUsed / s.dailyLimit) * 100);

  return (
    <section>
      <SectionHeader
        title="Automation Controls"
        subtitle="Govern what the Applier agent sends on your behalf"
      />

      <div className="rounded-xl border border-slate-200 bg-white p-4" style={{ boxShadow: TOKENS.shadow.card }}>
        {/* Master switch — elevated */}
        <div className="flex items-center justify-between gap-4 rounded-lg p-3 mb-2"
             style={{ background: s.autoApply ? 'oklch(0.97 0.02 255)' : '#F9FAFB', border: `1px solid ${s.autoApply ? 'oklch(0.88 0.05 255)' : '#EEF0F3'}` }}>
          <div className="flex items-center gap-3">
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg"
                 style={{ background: s.autoApply ? TOKENS.color.primary : '#E5E7EB', color: s.autoApply ? 'white' : '#6B7280' }}>
              <I.bolt s={16}/>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[14px] font-semibold text-slate-900">Auto-Apply mode</span>
                {s.autoApply
                  ? <Pill tone="success"><StatusDot tone="success" pulse size={6}/> On</Pill>
                  : <Pill tone="muted">Off</Pill>}
              </div>
              <div className="text-[12px] text-slate-500 mt-0.5">
                {s.autoApply
                  ? <>Applier will auto-submit to jobs scoring <span className="font-mono tabular-nums text-slate-800">{s.threshold}+</span> in matching roles.</>
                  : <>Matches are queued for your review. No applications sent.</>}
              </div>
            </div>
          </div>
          <Toggle on={s.autoApply} onChange={(v) => set({ autoApply: v })}/>
        </div>

        {/* Daily quota */}
        <div className="rounded-lg p-3 mb-1">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-[13px] font-medium text-slate-900">Daily application limit</div>
              <div className="text-[11.5px] text-slate-500">Protects deliverability and keeps applications tailored.</div>
            </div>
            <div className="text-right">
              <div className="text-[20px] font-semibold text-slate-900 font-mono tabular-nums leading-none">{s.dailyUsed}<span className="text-slate-400">/{s.dailyLimit}</span></div>
              <div className="text-[10.5px] uppercase tracking-wider text-slate-400 mt-1">submitted today</div>
            </div>
          </div>
          <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden mb-3">
            <div className="h-full rounded-full" style={{ width: `${dailyPct}%`, background: `linear-gradient(90deg, ${TOKENS.color.primary}, oklch(0.62 0.17 270))` }}/>
          </div>
          <Slider value={s.dailyLimit} onChange={(v) => set({ dailyLimit: v })} min={5} max={50} step={1}
            labelLeft="Cap per day" labelRight={`${s.dailyLimit} applications`}/>
        </div>

        {/* Threshold */}
        <div className="rounded-lg p-3 border-t border-slate-100">
          <Slider value={s.threshold} onChange={(v) => set({ threshold: v })} min={50} max={100} step={1}
            labelLeft="Minimum match score" labelRight={`${s.threshold} / 100`}/>
          <div className="mt-2 text-[11.5px] text-slate-500 leading-snug">
            Below this score, the Matcher routes jobs to your queue for manual review instead of auto-applying.
          </div>
        </div>

        {/* Detail switches */}
        <div className="mt-2">
          <Row title="Tailor cover letter per job"
               sub="Analyzer rewrites your letter to mirror the job description."
               control={<Toggle on={s.tailor} onChange={v=>set({tailor:v})}/>}/>
          <Row title="Skip previously-applied companies"
               sub="Don't re-apply to companies within a 90-day window."
               control={<Toggle on={s.skipDup} onChange={v=>set({skipDup:v})}/>}/>
          <Row title="Pause on first rejection today"
               sub="Stop automation if a screening rejects you — avoids burn-through."
               control={<Toggle on={s.pauseOnRej} onChange={v=>set({pauseOnRej:v})}/>}/>
          <Row title="Require my approval for salary &lt; target"
               sub={`Queue applications under $${s.salaryTarget}k for review.`}
               control={<Toggle on={s.approveLow} onChange={v=>set({approveLow:v})}/>}/>
        </div>

        <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
          <div className="text-[11.5px] text-slate-500 inline-flex items-center gap-1.5">
            <I.clock s={12}/> Next scheduled run in <span className="font-mono text-slate-900">12m 40s</span>
          </div>
          <Button variant="secondary" size="sm">Advanced rules</Button>
        </div>
      </div>
    </section>
  );
}

window.AutomationControls = AutomationControls;
window.Toggle = Toggle;
window.Slider = Slider;
