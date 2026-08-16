import { useState, useRef } from 'react';
import { analyzeCode, analyzeRepo } from '../api';
import FindingCard from './FindingCard';
import { SEVERITY_CONFIG } from './SeverityBadge';

const SAMPLE_CODE = `import requests
import asyncio

def fetch_data(url):
    return requests.get(url)

async def process_all(items):
    tasks = [handle(i) for i in items]
    return await asyncio.gather(*tasks)

def parse(data):
    try:
        return int(data)
    except:
        pass

def save_results(path, data):
    with open(path, "w") as f:
        f.write(data)
`;

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low'];

// Mirrors the real backend pipeline (ingest -> detect -> context_check ->
// explain, see agent.py). Durations here are a simulated approximation for
// the demo, not a live progress stream from the backend - but the stage
// order and names are the true architecture, not decorative.
const STAGES = [
  { id: 'ingest', label: 'Ingesting code' },
  { id: 'detect', label: 'Detecting reliability patterns' },
  { id: 'context', label: 'Searching repository for safe patterns' },
  { id: 'explain', label: 'Generating explanations' },
];

export default function AnalyzePanel() {
  const [mode, setMode] = useState('code'); // 'code' | 'repo'
  const [code, setCode] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [status, setStatus] = useState('idle'); // idle | loading | done | error
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const [activeStage, setActiveStage] = useState(0);
  const stageTimers = useRef([]);

  const clearStageTimers = () => {
    stageTimers.current.forEach(clearTimeout);
    stageTimers.current = [];
  };

  const runAnalysis = async () => {
    setStatus('loading');
    setError('');
    setReport(null);
    setActiveStage(0);

    // Advance through stages on a rough schedule while the real request is
    // in flight. If the response comes back before a later stage's timer
    // fires, that's fine - the timers get cleared once we have a result.
    const scheduleOffsets = mode === 'repo' ? [0, 1200, 3500, 6000] : [0, 500, 1400, 2200];
    scheduleOffsets.forEach((offset, i) => {
      const timer = setTimeout(() => setActiveStage(i), offset);
      stageTimers.current.push(timer);
    });

    try {
      const result = mode === 'code'
        ? await analyzeCode(code)
        : await analyzeRepo(repoUrl);
      clearStageTimers();
      setActiveStage(STAGES.length);
      setReport(result);
      setStatus('done');
    } catch (err) {
      clearStageTimers();
      setError(err.message || 'Something went wrong while analyzing.');
      setStatus('error');
    }
  };

  const canRun = mode === 'code' ? code.trim().length > 0 : repoUrl.trim().length > 0;

  const severityCounts = report
    ? report.findings.reduce((acc, f) => {
        acc[f.severity] = (acc[f.severity] || 0) + 1;
        return acc;
      }, {})
    : {};

  return (
    <div id="analyze" className="w-full">
      <div
        className="rounded-lg border overflow-hidden"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        {/* Tab bar */}
        <div className="flex items-center border-b" style={{ borderColor: 'var(--border)' }}>
          {[
            { id: 'code', label: 'Paste code' },
            { id: 'repo', label: 'GitHub repo URL' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setMode(tab.id)}
              className="font-mono text-xs px-4 py-3 border-b-2 transition-colors"
              style={{
                borderColor: mode === tab.id ? 'var(--accent)' : 'transparent',
                color: mode === tab.id ? 'var(--text)' : 'var(--text-muted)',
              }}
            >
              {tab.label}
            </button>
          ))}
          {mode === 'code' && (
            <button
              onClick={() => setCode(SAMPLE_CODE)}
              className="font-mono text-xs px-3 py-1 rounded ml-auto mr-3 border transition-colors hover:opacity-80"
              style={{ borderColor: 'var(--border)', color: 'var(--text-faint)' }}
            >
              load sample
            </button>
          )}
        </div>

        {/* Input area */}
        <div className="p-4">
          {mode === 'code' ? (
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Paste a Python file or snippet here..."
              spellCheck={false}
              rows={12}
              className="w-full font-mono text-sm p-3 rounded outline-none resize-y console-scroll"
              style={{ background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)' }}
            />
          ) : (
            <div>
              <label
                className="font-mono text-[10px] tracking-wider block mb-1.5"
                style={{ color: 'var(--text-faint)' }}
              >
                GITHUB REPOSITORY URL
              </label>
              <input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="w-full font-mono text-sm p-3 rounded outline-none"
                style={{ background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)' }}
              />
              <div
                className="font-mono text-[11px] mt-2 flex items-center gap-1.5"
                style={{ color: 'var(--text-faint)' }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent)' }} />
                Initial scan limit: 15 files, public repos only — larger repos are on the roadmap
              </div>
            </div>
          )}

          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={runAnalysis}
              disabled={!canRun || status === 'loading'}
              className="font-mono text-sm px-5 py-2.5 rounded font-medium transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: 'var(--accent)', color: 'var(--accent-text)' }}
            >
              {status === 'loading' ? 'analyzing…' : mode === 'repo' ? '▸ analyze repository' : '▸ run analysis'}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="mt-6">
        {status === 'loading' && (
          <div
            className="rounded-lg border p-5 font-mono text-sm space-y-2.5"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            {STAGES.map((stage, i) => {
              const isDone = i < activeStage;
              const isActive = i === activeStage;
              const isPending = i > activeStage;
              const dotColor = isDone
                ? 'var(--sev-safe)'
                : isActive
                ? 'var(--accent)'
                : 'var(--text-faint)';
              return (
                <div key={stage.id} className="flex items-center gap-2.5">
                  <span
                    className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isActive ? 'animate-blink' : ''}`}
                    style={{ background: dotColor, opacity: isPending ? 0.35 : 1 }}
                  />
                  <span style={{ color: isPending ? 'var(--text-faint)' : 'var(--text)', opacity: isPending ? 0.6 : 1 }}>
                    {isDone ? '✓' : isActive ? '●' : '○'} {stage.label}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {status === 'error' && (
          <div
            className="rounded-lg border p-4 text-sm font-mono"
            style={{ background: 'var(--sev-critical-bg)', borderColor: 'var(--sev-critical)', color: 'var(--sev-critical)' }}
          >
            {error}
          </div>
        )}

        {status === 'done' && report && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-display font-semibold text-sm">{report.summary}</span>
              <div className="flex gap-1.5 ml-2">
                {SEVERITY_ORDER.filter((s) => severityCounts[s]).map((s) => (
                  <span
                    key={s}
                    className="font-mono text-[10px] px-2 py-0.5 rounded"
                    style={{ color: SEVERITY_CONFIG[s].color, background: SEVERITY_CONFIG[s].bg }}
                  >
                    {severityCounts[s]} {s}
                  </span>
                ))}
              </div>
            </div>

            {report.findings.length === 0 ? (
              <div
                className="rounded-lg border p-6 text-center font-mono text-sm"
                style={{ background: 'var(--sev-safe-bg)', borderColor: 'var(--sev-safe)', color: 'var(--sev-safe)' }}
              >
                ✓ No reliability issues found in the 5 checked patterns.
              </div>
            ) : (
              report.findings.map((f, i) => <FindingCard key={i} finding={f} />)
            )}
          </div>
        )}
      </div>
    </div>
  );
}
