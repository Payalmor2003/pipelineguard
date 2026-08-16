const STAGES = [
  { id: '01', label: 'Ingest', detail: 'Read repo or pasted file' },
  { id: '02', label: 'Detect', detail: 'AST rules flag anti-patterns' },
  { id: '03', label: 'Context-check', detail: 'Hybrid retrieval scans repo for existing safe patterns' },
  { id: '04', label: 'Explain', detail: 'LLM writes the reasoning + fix, never the verdict' },
];

export default function PipelineStages() {
  return (
    <div className="flex flex-col sm:flex-row items-stretch gap-0">
      {STAGES.map((stage, i) => (
        <div key={stage.id} className="flex items-stretch flex-1">
          <div
            className="flex-1 rounded-md border px-4 py-4"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-mono text-xs" style={{ color: 'var(--accent)' }}>
                {stage.id}
              </span>
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: 'var(--sev-safe)' }}
              />
            </div>
            <div className="font-display font-semibold text-sm mb-1">{stage.label}</div>
            <div className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              {stage.detail}
            </div>
          </div>
          {i < STAGES.length - 1 && (
            <div
              className="hidden sm:flex items-center px-2 font-mono text-sm"
              style={{ color: 'var(--text-faint)' }}
            >
              →
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
