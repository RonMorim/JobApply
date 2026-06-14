// Tweaks panel — theme, density, auto-apply defaults

function Tweaks({ tweaks, setTweaks }) {
  const [open, setOpen] = React.useState(false);
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    const handler = (e) => {
      if (e.data?.type === '__activate_edit_mode')   { setVisible(true); setOpen(true); }
      if (e.data?.type === '__deactivate_edit_mode') { setVisible(false); setOpen(false); }
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', handler);
  }, []);

  const persist = (patch) => {
    const next = { ...tweaks, ...patch };
    setTweaks(next);
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits: patch }, '*');
  };

  if (!visible) return null;

  const accents = [
    { id: 'indigo', label: 'Trust',    color: 'oklch(0.55 0.18 255)' },
    { id: 'green',  label: 'Success',  color: 'oklch(0.60 0.15 155)' },
    { id: 'violet', label: 'Focus',    color: 'oklch(0.55 0.20 290)' },
    { id: 'navy',   label: 'Deep',     color: 'oklch(0.35 0.14 255)' },
  ];

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {open ? (
        <div className="w-[280px] rounded-xl bg-white border border-slate-200 shadow-xl overflow-hidden">
          <div className="flex items-center justify-between px-3 h-9 border-b border-slate-100 bg-slate-50">
            <div className="text-[12.5px] font-semibold text-slate-900">Tweaks</div>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-900"><I.x s={12}/></button>
          </div>
          <div className="p-3 space-y-3">
            <div>
              <div className="text-[10.5px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5">Brand accent</div>
              <div className="grid grid-cols-4 gap-1.5">
                {accents.map(a => (
                  <button key={a.id} onClick={() => persist({ accent: a.id })}
                    className={`rounded-md border p-1.5 flex flex-col items-center gap-1 ${tweaks.accent === a.id ? 'border-slate-900' : 'border-slate-200'}`}>
                    <span className="h-5 w-5 rounded" style={{ background: a.color }}/>
                    <span className="text-[10px] text-slate-600">{a.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="text-[10.5px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5">Match layout</div>
              <div className="inline-flex rounded-md border border-slate-200 p-0.5 w-full">
                {[
                  { id: 'list',   label: 'List' },
                  { id: 'compact',label: 'Compact' },
                ].map(o => (
                  <button key={o.id} onClick={() => persist({ matchLayout: o.id })}
                    className={`flex-1 h-7 text-[11.5px] rounded ${tweaks.matchLayout === o.id ? 'bg-slate-900 text-white' : 'text-slate-600'}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            <label className="flex items-center justify-between text-[12.5px] text-slate-800">
              <span>Show “Why this match”</span>
              <Toggle on={tweaks.showReasons} onChange={(v) => persist({ showReasons: v })}/>
            </label>
            <label className="flex items-center justify-between text-[12.5px] text-slate-800">
              <span>Include company logo tiles</span>
              <Toggle on={tweaks.showLogos} onChange={(v) => persist({ showLogos: v })}/>
            </label>
            <label className="flex items-center justify-between text-[12.5px] text-slate-800">
              <span>Dense rows</span>
              <Toggle on={tweaks.dense} onChange={(v) => persist({ dense: v })}/>
            </label>
          </div>
        </div>
      ) : (
        <button onClick={() => setOpen(true)} className="h-10 px-3 rounded-full bg-slate-900 text-white text-[12.5px] font-medium shadow-lg inline-flex items-center gap-1.5">
          <I.settings s={14}/> Tweaks
        </button>
      )}
    </div>
  );
}

window.Tweaks = Tweaks;
