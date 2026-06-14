// Top bar, sidebar, and page shell

function Sidebar({ current = 'dashboard', onNavigate }) {
  const navigate = onNavigate || (() => {});
  const items = [
    { id: 'dashboard', label: 'Dashboard',    icon: I.home,      count: null },
    { id: 'resume',    label: 'Resume & CV',  icon: I.file,      count: null },
    { id: 'apps',      label: 'Applications', icon: I.briefcase, count: null },
    { id: 'analytics', label: 'Analytics',    icon: I.chart,     count: null },
  ];
  return (
    <aside className="hidden lg:flex flex-col w-[220px] shrink-0 bg-white border-r border-slate-200 h-full">
      <div className="h-14 px-4 flex items-center border-b border-slate-100">
        <Logo/>
      </div>
      <nav className="p-2.5 flex-1">
        <div className="text-[10.5px] uppercase tracking-wider text-slate-400 font-semibold px-2.5 py-2">Workspace</div>
        {items.map(it => {
          const active = it.id === current;
          return (
            <button key={it.id}
              onClick={() => navigate(it.id)}
              className={`w-full flex items-center gap-2.5 px-2.5 h-8 rounded-md text-[13px] font-medium text-left transition ${active ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'}`}>
              <it.icon s={15}/>
              <span className="flex-1">{it.label}</span>
              {it.count != null && (
                <span className={`text-[11px] font-mono tabular-nums px-1.5 rounded ${active ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-500'}`}>
                  {it.count}
                </span>
              )}
            </button>
          );
        })}

        <div className="text-[10.5px] uppercase tracking-wider text-slate-400 font-semibold px-2.5 py-2 mt-4">Agents</div>
        {[
          { name: 'Scraper',  tone: 'success', pulse: true  },
          { name: 'Analyzer', tone: 'success', pulse: true  },
          { name: 'Matcher',  tone: 'warn',    pulse: false },
          { name: 'Applier',  tone: 'muted',   pulse: false },
        ].map(a => (
          <div key={a.name} className="flex items-center gap-2 px-2.5 h-7 text-[12.5px] text-slate-600">
            <StatusDot tone={a.tone} pulse={a.pulse} size={7}/>
            <span>{a.name}</span>
          </div>
        ))}
      </nav>

      <div className="p-2.5 border-t border-slate-100">
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-2.5">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-full bg-slate-900 text-white text-[11px] inline-flex items-center justify-center font-semibold">RM</div>
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-medium text-slate-900 truncate">Ron Morim</div>
              <div className="text-[11px] text-slate-500 truncate">Product & Operations</div>
            </div>
            <IconBtn><I.settings s={14}/></IconBtn>
          </div>
        </div>
      </div>
    </aside>
  );
}

const PAGE_TITLES = {
  dashboard: 'Dashboard',
  resume:    'Resume & CV',
  apps:      'Applications',
  analytics: 'Analytics',
};

function TopBar({ stats, page = 'dashboard' }) {
  const title = PAGE_TITLES[page] || 'Dashboard';
  return (
    <div className="h-14 shrink-0 bg-white border-b border-slate-200 flex items-center gap-3 px-5">
      <div className="flex items-center gap-2.5 flex-1 min-w-0">
        <h1 className="text-[15px] font-semibold text-slate-900 tracking-tight">{title}</h1>
        <span className="text-slate-300 text-[12px]">/</span>
        <span className="text-[12.5px] text-slate-500">Good morning, Ron</span>
      </div>

      <div className="hidden md:flex items-center gap-4 pr-3 border-r border-slate-200">
        <Stat label="Scanned" value={stats.scanned} />
        <Stat label="Matched" value={stats.matched} />
        <Stat label="Applied" value={stats.applied} tone="success"/>
      </div>

      <div className="relative hidden md:block">
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"><I.search s={14}/></span>
        <input placeholder="Search jobs, companies, skills…"
          className="h-8 w-64 rounded-md border border-slate-200 bg-slate-50 pl-8 pr-3 text-[12.5px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:bg-white"/>
        <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-mono text-slate-400 bg-white border border-slate-200 rounded px-1 py-0.5">⌘K</kbd>
      </div>

      <IconBtn title="Notifications"><I.bell s={16}/></IconBtn>
      <Button size="sm" icon={<I.plus s={13}/>}>Add source</Button>
    </div>
  );
}

function Stat({ label, value, tone }) {
  const c = tone === 'success' ? TOKENS.color.success : '#0B1220';
  return (
    <div className="flex flex-col leading-none">
      <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">{label}</span>
      <span className="text-[14px] font-semibold font-mono tabular-nums mt-0.5" style={{ color: c }}>{value}</span>
    </div>
  );
}

window.Sidebar = Sidebar;
window.TopBar  = TopBar;
