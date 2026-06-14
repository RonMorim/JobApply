// Agent Status Center — 4 agents with live-feel state, error/retry, and analysis trigger

function MiniBars({ values, color }) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex items-end gap-[2px] h-6">
      {values.map((v, i) => (
        <div key={i} className="rounded-sm" style={{
          width:      4,
          height:     `${Math.max(8, (v / max) * 100)}%`,
          background: color,
          opacity:    0.35 + (i / values.length) * 0.65,
        }}/>
      ))}
    </div>
  );
}

function AgentCard({ agent }) {
  const toneMap = {
    active: { tone: 'success', label: 'Active',  dot: 'success', pulse: true  },
    idle:   { tone: 'muted',   label: 'Idle',    dot: 'muted',   pulse: false },
    queued: { tone: 'warn',    label: 'Queued',  dot: 'warn',    pulse: false },
    error:  { tone: 'danger',  label: 'Error',   dot: 'danger',  pulse: true  },
    paused: { tone: 'muted',   label: 'Paused',  dot: 'muted',   pulse: false },
  };
  const s = toneMap[agent.state] || toneMap.idle;

  const accent = {
    Scraper:  TOKENS.color.primary,
    Analyzer: TOKENS.color.violet,
    Matcher:  TOKENS.color.success,
    Applier:  TOKENS.color.warn,
  }[agent.name] || TOKENS.color.primary;

  const IconComp = {
    Scraper:  I.scraper,
    Analyzer: I.analyzer,
    Matcher:  I.matcher,
    Applier:  I.applier,
  }[agent.name] || I.scraper;

  return (
    <div
      className="rounded-xl bg-white border border-slate-200 p-4 hover:shadow-sm transition-shadow"
      style={{ boxShadow: TOKENS.shadow.card }}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg shrink-0"
            style={{ background: `${accent}14`, color: accent }}
          >
            <IconComp s={18}/>
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-[14px] font-semibold text-slate-900">{agent.name}</span>
              <span className="text-[11px] text-slate-400 font-mono">#{agent.id}</span>
            </div>
            <div className="text-[12px] text-slate-500">{agent.role}</div>
          </div>
        </div>
        <Pill tone={s.tone}>
          <StatusDot tone={s.dot} pulse={s.pulse} size={6}/>
          {s.label}
        </Pill>
      </div>

      <div className="mt-3 text-[12px] text-slate-600 min-h-[32px] leading-snug">
        {agent.state === 'active' && (
          <span>
            <span className="inline-block w-1 h-1 rounded-full mr-1.5 align-middle" style={{ background: accent }}/>
            {agent.currentTask}
          </span>
        )}
        {agent.state === 'idle'   && <span className="text-slate-400">Waiting for upstream signal…</span>}
        {agent.state === 'queued' && <span>{agent.queueMsg}</span>}
        {agent.state === 'error'  && <span style={{ color: TOKENS.color.danger }}>{agent.errorMsg}</span>}
        {agent.state === 'paused' && <span className="text-slate-400">Paused by user.</span>}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 pt-3 border-t border-slate-100">
        <div>
          <div className="text-[10.5px] uppercase tracking-wider text-slate-400 font-medium mb-1">Today</div>
          <div className="text-[18px] font-semibold text-slate-900 font-mono tabular-nums leading-none">{agent.stats.today}</div>
        </div>
        <div>
          <div className="text-[10.5px] uppercase tracking-wider text-slate-400 font-medium mb-1">Queue</div>
          <div className="text-[18px] font-semibold text-slate-900 font-mono tabular-nums leading-none">{agent.stats.queue}</div>
        </div>
        <div>
          <div className="text-[10.5px] uppercase tracking-wider text-slate-400 font-medium mb-1">Throughput</div>
          <MiniBars values={agent.stats.spark} color={accent}/>
        </div>
      </div>
    </div>
  );
}

function AgentPipeline({ agents }) {
  return (
    <div className="flex items-center gap-1 text-[11px] text-slate-500 px-0.5 pt-1 flex-wrap">
      {agents.map((a, i) => (
        <React.Fragment key={a.id}>
          <span className="flex items-center gap-1">
            <StatusDot
              tone={
                a.state === 'active' ? 'success' :
                a.state === 'error'  ? 'danger'  :
                a.state === 'queued' ? 'warn'    : 'muted'
              }
              pulse={a.state === 'active' || a.state === 'error'}
              size={6}
            />
            <span className="font-medium text-slate-600">{a.name}</span>
          </span>
          {i < agents.length - 1 && <span className="text-slate-300 mx-1">→</span>}
        </React.Fragment>
      ))}
      <span className="ml-auto text-slate-400 font-mono tabular-nums">
        pipeline v1.2 · last sync 14:32:07
      </span>
    </div>
  );
}

// ── Error banner ──────────────────────────────────────────────────────────────

function AgentErrorBanner({ message, onRetry }) {
  return (
    <div
      className="rounded-xl border px-4 py-3 flex items-center justify-between gap-4 mb-3"
      style={{
        background:   TOKENS.color.dangerSoft,
        borderColor:  'oklch(0.88 0.07 25)',
      }}
    >
      <p className="text-[13px]" style={{ color: TOKENS.color.danger }}>
        <span className="font-semibold">Agent status unavailable</span>
        <span className="opacity-70"> — {message}</span>
      </p>
      <button
        onClick={onRetry}
        className="text-[12px] font-semibold underline underline-offset-2 shrink-0 transition-opacity hover:opacity-70"
        style={{ color: TOKENS.color.danger }}
      >
        Retry
      </button>
    </div>
  );
}

// ── Analyze trigger ───────────────────────────────────────────────────────────

function AnalyzeTrigger() {
  const [url,     setUrl]     = React.useState('');
  const [status,  setStatus]  = React.useState('idle');   // 'idle' | 'loading' | 'success' | 'error'
  const [message, setMessage] = React.useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setStatus('loading');
    setMessage('');

    try {
      const res = await fetch('http://127.0.0.1:8000/api/jobs/analyze-job', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ url: url.trim() }),
      });

      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const errBody = await res.json();
          detail = errBody.detail || detail;
        } catch (_) {}

        const isScrapeError = (
          res.status === 422 ||
          /scraping error|technical error reading|error occurred|no open positions|expired|removed|login/i.test(detail)
        );
        throw new Error(
          isScrapeError
            ? 'Technical error reading the job posting. The page may be expired, removed, or behind a login.'
            : detail
        );
      }

      const data = await res.json();

      setStatus('success');
      setMessage(`Analysis complete — ${data.title} @ ${data.company} · Match score: ${data.score}/100`);
      setUrl('');

    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Could not reach backend.');
    }
  };

  return (
    <div
      className="mt-3 rounded-xl border border-slate-200 bg-white p-4"
      style={{ boxShadow: TOKENS.shadow.card }}
    >
      <div className="flex items-center gap-2 mb-3">
        <I.spark s={14}/>
        <span className="text-[13px] font-semibold text-slate-900">Analyze a job URL</span>
        <span className="text-[12px] text-slate-400">Run the full 4-agent workflow</span>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder="https://jobs.lever.co/company/job-id"
          disabled={status === 'loading'}
          className="flex-1 h-9 rounded-md border border-slate-200 px-3 text-[13px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:border-transparent transition hover:border-slate-300"
          style={{ '--tw-ring-color': TOKENS.color.primary }}
        />
        <Button
          type="submit"
          size="sm"
          disabled={status === 'loading' || !url.trim()}
          icon={status === 'loading' ? null : <I.arrow s={13}/>}
        >
          {status === 'loading' ? 'Starting…' : 'Run'}
        </Button>
      </form>

      {message && (
        <p
          className="mt-2 text-[12px] leading-snug"
          style={{ color: status === 'error' ? TOKENS.color.danger : TOKENS.color.success }}
        >
          {message}
        </p>
      )}
      {status === 'success' && (
        <p className="mt-1 text-[11.5px] text-slate-400">
          Agent cards above update every 5 s as the pipeline progresses.
        </p>
      )}
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

function AgentStatusCenter({ agents, error, onRetry }) {
  const anyActive  = agents.some(a => a.state === 'active' || a.state === 'queued');
  const allNominal = agents.length > 0 && agents.every(a => a.state !== 'error');

  return (
    <section>
      <SectionHeader
        title="Agent Status Center"
        subtitle="Live state of the 4-stage automation pipeline"
        right={
          <div className="flex items-center gap-2">
            {!error && anyActive && (
              <Pill tone="primary">
                <StatusDot tone="primary" pulse size={6}/> Pipeline running
              </Pill>
            )}
            {!error && allNominal && !anyActive && (
              <Pill tone="success">
                <StatusDot tone="success" pulse size={6}/> All systems nominal
              </Pill>
            )}
            {error && (
              <Pill tone="danger">
                <StatusDot tone="danger" pulse size={6}/> System error
              </Pill>
            )}
            <Button variant="secondary" size="sm" icon={<I.settings s={14}/>}>Configure</Button>
          </div>
        }
      />

      {error && <AgentErrorBanner message={error} onRetry={onRetry}/>}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {agents.map(a => <AgentCard key={a.id} agent={a}/>)}
      </div>

      <AgentPipeline agents={agents}/>
      <AnalyzeTrigger/>
    </section>
  );
}

window.AgentStatusCenter = AgentStatusCenter;
window.AgentCard = AgentCard;