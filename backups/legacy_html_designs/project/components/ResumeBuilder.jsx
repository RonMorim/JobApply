// Resume Builder — generate tailored, design-varied resumes per job

const _ACCEPTED_MIME = new Set([
  'image/jpeg', 'image/png', 'image/webp', 'image/gif',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

function _fileTypeLabel(file) {
  if (!file) return null;
  if (file.type.startsWith('image/')) return 'Image';
  if (file.type === 'application/pdf') return 'PDF';
  if (file.name.endsWith('.docx') || file.type.includes('wordprocessingml')) return 'Word';
  return file.type || 'File';
}

function UploadZone({ file, onChange }) {
  const inputRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && (_ACCEPTED_MIME.has(f.type) || f.name.endsWith('.docx') || f.name.endsWith('.pdf')))
      onChange(f);
  };

  const typeTag  = _fileTypeLabel(file);
  const label    = file ? file.name : 'Drop a file here or click to upload';
  const sub      = file
    ? `${(file.size / 1024).toFixed(0)} KB · ${typeTag}`
    : 'Image · PDF · Word (.docx) · max 10 MB · optional';

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className="rounded-lg border-2 border-dashed cursor-pointer transition-all p-4 flex flex-col items-center justify-center gap-2 text-center select-none"
      style={{
        borderColor: dragging ? TOKENS.color.primary : TOKENS.color.line,
        background:  dragging ? TOKENS.color.primarySoft : TOKENS.color.lineSoft,
        minHeight: 80,
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*,application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        onChange={(e) => e.target.files[0] && onChange(e.target.files[0])}
      />
      <div className="text-[12.5px] font-medium text-slate-700 truncate max-w-full px-2">{label}</div>
      <div className="text-[11px] text-slate-400">{sub}</div>
      {file && (
        <button
          onClick={(e) => { e.stopPropagation(); onChange(null); }}
          className="text-[11px] text-rose-500 hover:text-rose-700 underline mt-1"
        >
          Remove
        </button>
      )}
    </div>
  );
}

function MissingDataForm({ questions, answers, onChange, onRegenerate, loading }) {
  if (!questions || questions.length === 0) return null;
  return (
    <div
      className="rounded-xl border p-4 space-y-4"
      style={{ background: TOKENS.color.warnSoft, borderColor: 'oklch(0.86 0.09 80)' }}
    >
      <div className="flex items-center gap-2">
        <div
          className="h-6 w-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0"
          style={{ background: TOKENS.color.warn, color: '#fff' }}
        >
          {questions.length}
        </div>
        <div>
          <div className="text-[13px] font-semibold text-slate-800">
            Missing information
          </div>
          <div className="text-[11.5px] text-slate-500">
            Answer any or all below, then regenerate.
          </div>
        </div>
      </div>

      {questions.map((q) => (
        <div key={q.id} className="space-y-1">
          <label className="block text-[12.5px] font-medium text-slate-700">{q.question}</label>
          <div className="text-[11px] text-slate-400 italic mb-1">{q.context}</div>
          <textarea
            rows={2}
            value={answers[q.id] || ''}
            onChange={(e) => onChange(q.id, e.target.value)}
            placeholder="Your answer…"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-[12.5px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 resize-none"
            style={{ focusRingColor: TOKENS.color.primary }}
          />
        </div>
      ))}

      <Button
        size="sm"
        onClick={onRegenerate}
        disabled={loading}
        icon={loading ? null : <I.spark s={13}/>}
      >
        {loading ? 'Regenerating…' : 'Regenerate with answers'}
      </Button>
    </div>
  );
}

function ResumePreview({ html }) {
  if (!html) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-white"
           style={{ boxShadow: TOKENS.shadow.card, minHeight: 480 }}>
        <div className="h-16 w-16 rounded-2xl flex items-center justify-center"
             style={{ background: TOKENS.color.lineSoft, color: TOKENS.color.muted }}>
          <I.file s={28}/>
        </div>
        <div className="text-center">
          <p className="text-[13.5px] font-medium text-slate-700">No resume generated yet</p>
          <p className="text-[12px] text-slate-400 mt-1 max-w-[28ch] leading-relaxed">
            Select a job and click Generate to create a tailored, unique resume.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col rounded-xl border border-slate-200 overflow-hidden"
         style={{ boxShadow: TOKENS.shadow.card, minHeight: 480 }}>
      <iframe
        srcDoc={html}
        title="Resume Preview"
        className="flex-1 w-full border-0"
        style={{ minHeight: 640 }}
        sandbox="allow-same-origin"
      />
    </div>
  );
}

function ResumeBuilder({ jobs = [] }) {
  const [jobId,        setJobId]        = React.useState(jobs[0]?.id || '');
  const [refImage,     setRefImage]     = React.useState(null);
  const [loading,      setLoading]      = React.useState(false);
  const [error,        setError]        = React.useState(null);
  const [result,       setResult]       = React.useState(null);   // { html, missing_data_requests, layout_variant }
  const [answers,      setAnswers]      = React.useState({});

  // Keep jobId in sync if jobs list changes after initial render
  React.useEffect(() => {
    if (!jobId && jobs.length > 0) setJobId(jobs[0].id);
  }, [jobs]);

  const selectedJob = jobs.find(j => j.id === jobId);

  async function submit(supplementalAnswers = {}) {
    if (!jobId) { setError('Please select a job first.'); return; }
    setLoading(true);
    setError(null);

    const form = new FormData();
    form.append('job_id', jobId);
    form.append('supplemental_answers_json', JSON.stringify(supplementalAnswers));
    if (refImage) form.append('reference_file', refImage);

    try {
      const res  = await fetch('http://127.0.0.1:8000/api/resumes/generate', {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setResult(data);
    } catch (err) {
      setError(err.message || 'Generation failed. Is the backend running?');
    } finally {
      setLoading(false);
    }
  }

  function handleAnswerChange(id, value) {
    setAnswers(prev => ({ ...prev, [id]: value }));
  }

  function handleDownload() {
    if (!result?.html) return;
    const blob = new Blob([result.html], { type: 'text/html' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `resume-${jobId}.html`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="max-w-[1440px] mx-auto p-5 lg:p-6">
      <SectionHeader
        title="Resume Builder"
        subtitle="AI-tailored resume — unique layout generated per job"
        right={
          result?.html && (
            <div className="flex items-center gap-2">
              {result.layout_variant && (
                <Pill tone="primary">{result.layout_variant}</Pill>
              )}
              <Button variant="secondary" size="sm" onClick={handleDownload} icon={<I.ext s={13}/>}>
                Download HTML
              </Button>
            </div>
          )
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-6 mt-4">

        {/* ── Left panel: controls ─────────────────────────────────────── */}
        <div className="space-y-4">

          {/* Job selector */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3"
               style={{ boxShadow: TOKENS.shadow.card }}>
            <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
              Target Job
            </div>
            {jobs.length === 0 ? (
              <p className="text-[12.5px] text-slate-400 italic">
                No jobs in database yet — run the discovery pipeline first.
              </p>
            ) : (
              <select
                value={jobId}
                onChange={(e) => { setJobId(e.target.value); setResult(null); setAnswers({}); }}
                className="w-full rounded-md border border-slate-200 bg-slate-50 px-3 h-9 text-[13px] text-slate-900 focus:outline-none focus:ring-2"
              >
                {jobs.map(j => (
                  <option key={j.id} value={j.id}>
                    {j.title} — {j.company} ({j.score?.toFixed ? j.score.toFixed(1) : j.score}/100)
                  </option>
                ))}
              </select>
            )}

            {selectedJob && (
              <div className="text-[11.5px] text-slate-500 space-y-0.5">
                <div className="flex items-center gap-1.5">
                  <I.pin s={11}/>
                  <span>{selectedJob.location}</span>
                </div>
                {selectedJob.reasons?.slice(0, 3).map((r, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-slate-400">
                    <I.check s={10}/>
                    <span>{r.label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Reference design upload */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3"
               style={{ boxShadow: TOKENS.shadow.card }}>
            <div>
              <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
                Design Reference
              </div>
              <div className="text-[11.5px] text-slate-400 mt-0.5">
                Upload an image, PDF, or Word (.docx) resume to mimic its layout.
              </div>
            </div>
            <UploadZone file={refImage} onChange={setRefImage}/>
          </div>

          {/* Generate button */}
          <Button
            size="lg"
            className="w-full justify-center"
            onClick={() => submit({})}
            disabled={loading || !jobId}
            icon={loading ? null : <I.spark s={15}/>}
          >
            {loading ? 'Generating resume…' : 'Generate Resume'}
          </Button>

          {error && (
            <div
              className="rounded-lg px-3 py-2.5 text-[12.5px]"
              style={{ background: TOKENS.color.dangerSoft, color: 'oklch(0.42 0.14 25)' }}
            >
              {error}
            </div>
          )}

          {/* Missing data form */}
          {result && (
            <MissingDataForm
              questions={result.missing_data_requests}
              answers={answers}
              onChange={handleAnswerChange}
              onRegenerate={() => submit(answers)}
              loading={loading}
            />
          )}
        </div>

        {/* ── Right panel: preview ─────────────────────────────────────── */}
        <ResumePreview html={result?.html || null}/>
      </div>
    </div>
  );
}

window.ResumeBuilder = ResumeBuilder;
