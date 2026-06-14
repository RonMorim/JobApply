// Application Tracker — ATS pipeline view

const STAGES = [
  { id: 'submitted',  label: 'Submitted',   tone: 'muted' },
  { id: 'viewed',     label: 'Viewed',      tone: 'primary' },
  { id: 'screening',  label: 'Screening',   tone: 'primary' },
  { id: 'interview',  label: 'Interview',   tone: 'violet' },
  { id: 'offer',      label: 'Offer',       tone: 'success' },
  { id: 'rejected',   label: 'Rejected',    tone: 'danger' },
];

function StageBar({ stage }) {
  const idx = STAGES.findIndex(s => s.id === stage);
  if (stage === 'rejected') {
    return (
      <div className="flex items-center gap-0.5 w-full">
        {STAGES.slice(0,5).map((s,i) => (
          <div key={s.id} className="flex-1 h-1 rounded-full" style={{ background: '#FEE2E2' }}/>
        ))}
      </div>
    );
  }
  return (
    <div className="flex items-center gap-0.5 w-full">
      {STAGES.slice(0,5).map((s,i) => (
        <div key={s.id} className="flex-1 h-1 rounded-full"
             style={{ background: i <= idx ? TOKENS.color.primary : '#EEF0F3' }}/>
      ))}
    </div>
  );
}

function StageBadge({ stage }) {
  const map = {
    submitted: { tone: 'muted',   label: 'Submitted' },
    viewed:    { tone: 'primary', label: 'Viewed by recruiter' },
    screening: { tone: 'primary', label: 'In screening' },
    interview: { tone: 'violet',  label: 'Interview scheduled' },
    offer:     { tone: 'success', label: 'Offer extended' },
    rejected:  { tone: 'danger',  label: 'Rejected' },
  };
  const s = map[stage];
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

function TrackerRow({ app }) {
  return (
    <div className="px-4 py-3 hover:bg-slate-50 transition-colors">
      <div className="flex items-center gap-3">
        <CompanyLogo company={app.company}/>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13.5px] font-medium text-slate-900 truncate">{app.title}</span>
            <span className="text-[12px] text-slate-500">· {app.company}</span>
          </div>
          <div className="flex items-center gap-2 text-[11.5px] text-slate-500 mt-0.5">
            <span className="font-mono tabular-nums">{app.submittedAt}</span>
            <span className="text-slate-300">·</span>
            <span>ATS: {app.ats}</span>
            <span className="text-slate-300">·</span>
            <span className="inline-flex items-center gap-1">
              Match <span className="font-mono tabular-nums font-medium text-slate-700">{app.score}</span>
            </span>
          </div>
        </div>
        <div className="shrink-0 w-44 hidden md:block">
          <StageBar stage={app.stage}/>
          <div className="text-[10.5px] text-slate-400 font-mono tabular-nums mt-1.5 text-right">
            {app.lastUpdate}
          </div>
        </div>
        <div className="shrink-0">
          <StageBadge stage={app.stage}/>
        </div>
      </div>
    </div>
  );
}

function TrackerStats({ apps }) {
  const total = apps.length;
  const active = apps.filter(a => !['rejected','offer'].includes(a.stage)).length;
  const interviews = apps.filter(a => a.stage === 'interview' || a.stage === 'offer').length;
  const replyRate = Math.round((apps.filter(a => ['viewed','screening','interview','offer'].includes(a.stage)).length / total) * 100);
  const items = [
    { label: 'Applications this week', value: total, accent: TOKENS.color.primary },
    { label: 'Active in pipeline',     value: active, accent: TOKENS.color.violet  },
    { label: 'Interviews landed',      value: interviews, accent: TOKENS.color.success },
    { label: 'Response rate',          value: `${replyRate}%`, accent: TOKENS.color.warn },
  ];
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mb-3">
      {items.map(s => (
        <div key={s.label} className="rounded-xl bg-white border border-slate-200 p-3" style={{ boxShadow: TOKENS.shadow.card }}>
          <div className="flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-wider text-slate-400 font-medium">{s.label}</div>
            <div className="h-1.5 w-1.5 rounded-full" style={{ background: s.accent }}/>
          </div>
          <div className="mt-1.5 text-[24px] font-semibold text-slate-900 font-mono tabular-nums leading-none">{s.value}</div>
        </div>
      ))}
    </div>
  );
}

function ApplicationTracker({ apps = [] }) {
  return (
    <section>
      <SectionHeader
        title="Application Tracker"
        subtitle="Applier submissions, with live ATS pull-through"
        right={
          apps.length > 0 && (
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm">Export CSV</Button>
              <Button variant="ghost" size="sm">View all →</Button>
            </div>
          )
        }
      />
      {apps.length === 0 ? (
        <div className="rounded-xl bg-white border border-slate-200 py-12 text-center" style={{ boxShadow: TOKENS.shadow.card }}>
          <div className="text-[13px] text-slate-400">No applications submitted yet.</div>
          <div className="text-[12px] text-slate-300 mt-1">Applications will appear here once the Applier agent is active.</div>
        </div>
      ) : (
        <>
          <TrackerStats apps={apps}/>
          <div className="rounded-xl bg-white border border-slate-200 overflow-hidden" style={{ boxShadow: TOKENS.shadow.card }}>
            <div className="px-4 py-2.5 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
              <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">Recent submissions</div>
              <div className="text-[11px] text-slate-500 font-mono tabular-nums">Synced 14:32</div>
            </div>
            <div className="divide-y divide-slate-100">
              {apps.map(a => <TrackerRow key={a.id} app={a}/>)}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

window.ApplicationTracker = ApplicationTracker;
