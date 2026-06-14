// Analysis Report Drawer — slides in from right, Escape + backdrop close

function parseReport(raw) {
  const lines = raw.split('\n');
  const blocks = [];
  for (let i = 0; i < lines.length; i++) {
    const line  = lines[i];
    const tr    = line.trim();
    if (!tr) {
      if (blocks.length && blocks[blocks.length - 1].type !== 'spacer')
        blocks.push({ type: 'spacer' });
      continue;
    }
    if (tr.startsWith('# '))                                                         { blocks.push({ type: 'h1',             text: tr.slice(2) });                                              continue; }
    if (tr.startsWith('—') && tr.endsWith('—'))                                      { blocks.push({ type: 'subtitle',       text: tr.replace(/^—\s*/,'').replace(/\s*—$/,'') });               continue; }
    if (/^━{10,}/.test(tr))                                                          { blocks.push({ type: 'divider' });                                                                        continue; }
    if (!tr.startsWith('★') && tr === tr.toUpperCase() && tr.length >= 3 && /[A-Z]/.test(tr)) { blocks.push({ type: 'section-heading', text: tr });                                           continue; }
    if (tr.startsWith('★'))                                                          { blocks.push({ type: 'stars',          text: tr });                                                       continue; }
    const num = tr.match(/^(\d+)\.\s+(.+)/);
    if (num)                                                                         { blocks.push({ type: 'numbered',       n: parseInt(num[1]), text: num[2] });                               continue; }
    if (line.startsWith('  ') && tr.includes(':') && tr.length < 160)               { blocks.push({ type: 'meta',           text: tr });                                                       continue; }
    blocks.push({ type: 'body', text: tr });
  }
  return blocks;
}

function renderReportBlock(block, idx) {
  switch (block.type) {
    case 'h1':
      return <h1 key={idx} className="text-[18px] font-bold text-slate-900 leading-snug mt-2">{block.text}</h1>;

    case 'subtitle':
      return <p key={idx} className="text-[12.5px] text-slate-400 font-medium tracking-wide mt-1">{block.text}</p>;

    case 'divider':
      return <hr key={idx} className="border-slate-200 my-5"/>;

    case 'section-heading':
      return (
        <h2 key={idx} className="text-[10.5px] font-bold tracking-widest uppercase mt-5 mb-2"
            style={{ color: TOKENS.color.muted }}>
          {block.text}
        </h2>
      );

    case 'stars': {
      const m = block.text.match(/^(★+(?:☆*))\s+(.+)/);
      if (m) {
        return (
          <div key={idx} className="flex items-center gap-2 mt-4 mb-1">
            <span className="text-[14px] tracking-tighter" style={{ color: TOKENS.color.warn }}>{m[1]}</span>
            <span className="text-[13px] font-semibold text-slate-800">{m[2]}</span>
          </div>
        );
      }
      return <p key={idx} className="text-[13px] text-slate-700">{block.text}</p>;
    }

    case 'meta': {
      const ci = block.text.indexOf(':');
      if (ci > -1) {
        return (
          <div key={idx} className="flex gap-3 text-[12.5px] leading-relaxed pl-4 my-0.5">
            <span className="text-slate-400 shrink-0 min-w-[100px]">{block.text.slice(0, ci).trim()}</span>
            <span className="text-slate-700">{block.text.slice(ci + 1).trim()}</span>
          </div>
        );
      }
      return <p key={idx} className="text-[12.5px] text-slate-600 pl-4">{block.text}</p>;
    }

    case 'numbered':
      return (
        <div key={idx} className="flex gap-3 text-[13px] leading-relaxed text-slate-700 my-1.5">
          <span className="shrink-0 w-5 text-right font-semibold font-mono" style={{ color: TOKENS.color.primary }}>
            {block.n}.
          </span>
          <span>{block.text}</span>
        </div>
      );

    case 'body':
      return <p key={idx} className="text-[13px] leading-relaxed text-slate-700">{block.text}</p>;

    case 'spacer':
      return <div key={idx} className="h-2"/>;

    default:
      return null;
  }
}

function ReportDrawer({ job, onClose }) {
  const scrollRef = React.useRef(null);

  // Reset scroll on new job
  React.useEffect(() => {
    if (job && scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [job?.id]);

  // Escape key
  React.useEffect(() => {
    if (!job) return;
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [job, onClose]);

  const isOpen = !!job;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 z-40 transition-opacity duration-300"
        style={{
          background:    'rgba(11,18,32,0.45)',
          backdropFilter:'blur(2px)',
          opacity:       isOpen ? 1 : 0,
          pointerEvents: isOpen ? 'auto' : 'none',
        }}
      />

      {/* Panel */}
      <div
        className="fixed top-0 right-0 bottom-0 z-50 flex flex-col bg-white"
        style={{
          width:      'min(600px, 100vw)',
          boxShadow:  TOKENS.shadow.pop,
          transform:  isOpen ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 300ms cubic-bezier(0.32,0,0.15,1)',
        }}
      >
        {/* Sticky header */}
        <div className="shrink-0 px-6 py-4 border-b border-slate-200 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[10.5px] font-semibold tracking-widest uppercase" style={{ color: TOKENS.color.muted }}>
              Analysis Report
            </p>
            {job && (
              <>
                <h2 className="text-[15px] font-bold text-slate-900 leading-tight mt-1 truncate">
                  {job.title}
                </h2>
                <p className="text-[12.5px] text-slate-500 mt-0.5">
                  {job.company}{job.location ? ` · ${job.location}` : ''}
                </p>
              </>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0 mt-0.5">
            {job && (
              <div
                className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md text-[12.5px] font-bold font-mono tabular-nums"
                style={{ background: TOKENS.color.primarySoft, color: TOKENS.color.primaryInk }}
              >
                {job.score}<span className="font-normal opacity-60">/100</span>
              </div>
            )}
            <IconBtn onClick={onClose} title="Close (Esc)">
              <I.x s={15}/>
            </IconBtn>
          </div>
        </div>

        {/* Scrollable body */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-5">
          {!job ? null : !job.whyRon ? (
            <div className="h-full flex flex-col items-center justify-center gap-3 text-center py-16">
              <div
                className="inline-flex h-14 w-14 items-center justify-center rounded-xl"
                style={{ background: TOKENS.color.lineSoft, color: TOKENS.color.muted }}
              >
                <I.file s={24}/>
              </div>
              <p className="text-[13px] text-slate-500 max-w-[26ch] leading-relaxed">
                No analysis report available for this job.
              </p>
              <p className="text-[12px] text-slate-400 max-w-[34ch] leading-relaxed">
                Run the analysis pipeline on this URL to generate a full recruiter brief.
              </p>
            </div>
          ) : (
            <div className="space-y-0">
              {parseReport(job.whyRon).map((block, i) => renderReportBlock(block, i))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

window.ReportDrawer = ReportDrawer;
