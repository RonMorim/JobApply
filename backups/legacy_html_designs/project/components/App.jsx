// Main Dashboard composition

// Map an Application from the API to the shape ApplicationTracker expects.
function normalizeApp(a) {
  return {
    id:          a.application_id,
    title:       a.title,
    company:     a.company,
    ats:         a.ats,
    submittedAt: a.submitted_at,
    lastUpdate:  a.last_update,
    stage:       a.status,
    score:       a.score,
  };
}

// Map a JobMatch from the API to the shape the UI components expect.
function normalizeJob(j) {
  return {
    id:       j.job_id,
    title:    j.title,
    company:  j.company,
    location: j.location,
    remote:   /remote/i.test(j.location || ''),
    salary:   null,
    posted:   j.posted_at  || 'recently',
    score:    j.score,
    isNew:    j.is_new,
    isOpen:   j.is_open  !== false,
    source:   j.source   || 'automatic',
    reasons:  (j.reasons || []).map(r => ({ kind: r.kind, label: r.label })),
    applyUrl:         j.apply_url         || null,
    whyRon:           j.why_ron           || null,
    category:         j.category          || null,
    scoringRationale: j.scoring_rationale || null,
  };
}

function Dashboard() {
  const [page,            setPage]            = React.useState('dashboard');
  const [agents,          setAgents]          = React.useState(AGENTS);
  const [jobs,            setJobs]            = React.useState([]);
  const [apps,            setApps]            = React.useState([]);
  const [selected,        setSelected]        = React.useState(null);
  const [savedIds,        setSavedIds]        = React.useState([]);
  const [reviewJob,       setReviewJob]       = React.useState(null);
  const [agentError,      setAgentError]      = React.useState(null);
  const [categories,      setCategories]      = React.useState([]);
  const [categoryFilter,  setCategoryFilter]  = React.useState('all');
  const [minScore,        setMinScore]        = React.useState(0);
  const [sourceFilter,    setSourceFilter]    = React.useState('all');

  // Fetch jobs, categories, and applications from the backend.
  React.useEffect(() => {
    function fetchJobs() {
      fetch('http://127.0.0.1:8000/api/jobs/')
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .then(data => {
          const normalized = data.map(normalizeJob);
          setJobs(normalized);
          setSelected(prev => prev ?? (normalized[0]?.id ?? null));
        })
        .catch(err => {
          console.warn('[MatchFeed] API unavailable:', err);
        });
    }
    function fetchCategories() {
      fetch('http://127.0.0.1:8000/api/jobs/categories')
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .then(data => setCategories(data))
        .catch(() => {});
    }
    function fetchApps() {
      fetch('http://127.0.0.1:8000/api/applications/')
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .then(data => setApps(data.map(normalizeApp)))
        .catch(() => {});
    }
    fetchJobs();
    fetchCategories();
    fetchApps();
    const interval = setInterval(() => { fetchJobs(); fetchCategories(); fetchApps(); }, 30000);
    return () => clearInterval(interval);
  }, []);
  const [settings,   setSettings]   = React.useState({
    autoApply: true,
    threshold: 85,
    dailyLimit: 15,
    dailyUsed: 8,
    tailor: true,
    skipDup: true,
    pauseOnRej: false,
    approveLow: true,
    salaryTarget: 170,
  });
  const [tweaks, setTweaks] = React.useState(window.TWEAK_DEFAULTS || {
    accent: 'indigo',
    matchLayout: 'list',
    showReasons: true,
    showLogos: true,
    dense: false,
  });

  // Apply tweak: accent color
  React.useEffect(() => {
    const map = {
      indigo: 'oklch(0.55 0.18 255)',
      green:  'oklch(0.60 0.15 155)',
      violet: 'oklch(0.55 0.20 290)',
      navy:   'oklch(0.35 0.14 255)',
    };
    window.TOKENS.color.primary = map[tweaks.accent] || map.indigo;
    document.documentElement.style.setProperty('--ja-primary', map[tweaks.accent] || map.indigo);
  }, [tweaks.accent]);

  // Live-feel: rotate Scraper task text
  React.useEffect(() => {
    const tasks = [
      'Crawling LinkedIn · "Senior Product Designer" · page 4/12',
      'Fetching Greenhouse · "Design Systems Lead" · 18 results',
      'Scanning Ashby · "Staff Designer, Platform" · page 2/6',
      'Polling Lever · "Principal UX" · 22 new postings',
    ];
    let i = 0;
    const t = setInterval(() => {
      i = (i + 1) % tasks.length;
      setAgents(curr => curr.map(a => a.name === 'Scraper' ? { ...a, currentTask: tasks[i] } : a));
    }, 2600);
    return () => clearInterval(t);
  }, []);

  const onDismiss   = (id) => setJobs(jobs.filter(j => j.id !== id));
  const onApply     = (id) => {
    setJobs(jobs.filter(j => j.id !== id));
    setSettings(s => ({ ...s, dailyUsed: Math.min(s.dailyLimit, s.dailyUsed + 1) }));
  };
  const onSave      = (id) => setSavedIds(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  const onReviewCV  = (id) => setReviewJob(jobs.find(j => j.id === id) ?? null);

  const stats = { scanned: '2,481', matched: jobs.length, applied: apps.length };

  return (
    <div className="h-screen w-screen flex bg-[#F7F8FA] text-slate-900 overflow-hidden">
      <Sidebar current={page} onNavigate={setPage}/>
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar stats={stats} page={page}/>
        <main className="flex-1 overflow-y-auto">

          {/* ── Dashboard ── */}
          {page === 'dashboard' && (
            <div className="max-w-[1440px] mx-auto p-5 lg:p-6 space-y-6">
              <AgentStatusCenter agents={agents} error={agentError} onRetry={() => setAgentError(null)}/>
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2 space-y-6">
                  <MatchFeed
                    jobs={jobs}
                    selected={selected}
                    setSelected={setSelected}
                    onDismiss={onDismiss}
                    onApply={onApply}
                    savedIds={savedIds}
                    onSave={onSave}
                    onReviewCV={onReviewCV}
                    categories={categories}
                    categoryFilter={categoryFilter}
                    setCategoryFilter={setCategoryFilter}
                    minScore={minScore}
                    setMinScore={setMinScore}
                    sourceFilter={sourceFilter}
                    setSourceFilter={setSourceFilter}/>
                  <ApplicationTracker apps={apps}/>
                </div>
                <div className="space-y-6">
                  <AutomationControls settings={settings} setSettings={setSettings}/>
                  <ActivityFeed/>
                </div>
              </div>
              <footer className="text-[11px] text-slate-400 pt-2 pb-6 flex items-center justify-between">
                <span>Job Apply · v1.2.0 · pipeline synced 14:32:07 UTC</span>
                <span className="font-mono">© 2026 Job Apply Systems</span>
              </footer>
            </div>
          )}

          {/* ── Resume Builder ── */}
          {page === 'resume' && (
            <ResumeBuilder jobs={jobs}/>
          )}

          {/* ── Applications (placeholder) ── */}
          {page === 'apps' && (
            <div className="max-w-[1440px] mx-auto p-5 lg:p-6">
              <ApplicationTracker apps={apps}/>
            </div>
          )}

          {/* ── Analytics (placeholder) ── */}
          {page === 'analytics' && (
            <div className="max-w-[1440px] mx-auto p-5 lg:p-6 flex items-center justify-center" style={{ minHeight: 400 }}>
              <div className="text-center">
                <div className="h-14 w-14 rounded-2xl mx-auto flex items-center justify-center mb-3"
                     style={{ background: TOKENS.color.lineSoft, color: TOKENS.color.muted }}>
                  <I.chart s={24}/>
                </div>
                <p className="text-[13.5px] font-medium text-slate-700">Analytics coming soon</p>
                <p className="text-[12px] text-slate-400 mt-1">Pipeline metrics will appear here once more data is collected.</p>
              </div>
            </div>
          )}

        </main>
      </div>
      <Tweaks tweaks={tweaks} setTweaks={setTweaks}/>
      <ReportDrawer job={reviewJob} onClose={() => setReviewJob(null)}/>
    </div>
  );
}

// Live activity feed — small sidebar component for dashboard right column
function ActivityFeed() {
  const events = [
    { time: '14:32', who: 'Applier',  text: 'Submitted application to Cedar Labs', tone: 'success' },
    { time: '14:28', who: 'Matcher',  text: 'New 94% match: Linear Orbit',          tone: 'primary' },
    { time: '14:14', who: 'Analyzer', text: 'Parsed 12 postings from Greenhouse',   tone: 'muted'   },
    { time: '14:02', who: 'Scraper',  text: 'Added 48 postings from LinkedIn',      tone: 'muted'   },
    { time: '13:47', who: 'Applier',  text: 'Northfield · tailored cover letter',   tone: 'primary' },
    { time: '13:31', who: 'Matcher',  text: 'Dismissed 6 low-fit matches',          tone: 'muted'   },
  ];
  return (
    <section>
      <SectionHeader title="Live activity" subtitle="Real-time pipeline events"/>
      <div className="rounded-xl bg-white border border-slate-200" style={{ boxShadow: TOKENS.shadow.card }}>
        <ul className="divide-y divide-slate-100">
          {events.map((e, i) => (
            <li key={i} className="px-4 py-2.5 flex items-start gap-3">
              <span className="text-[11px] font-mono text-slate-400 tabular-nums w-10 mt-0.5">{e.time}</span>
              <StatusDot tone={e.tone} pulse={i === 0} size={6}/>
              <div className="flex-1 min-w-0">
                <div className="text-[12.5px] text-slate-800">{e.text}</div>
                <div className="text-[11px] text-slate-400 mt-0.5">{e.who} agent</div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<Dashboard/>);
