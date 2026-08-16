import { useState } from 'react';
import SeverityBadge from './SeverityBadge';

export default function FindingCard({ finding }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="rounded-md border overflow-hidden"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3 flex items-center gap-3 flex-wrap"
      >
        <SeverityBadge severity={finding.severity} />
        <span className="font-display font-medium text-sm">{finding.title}</span>
        <span
          className="font-mono text-[10px] px-1.5 py-0.5 rounded"
          style={{ color: 'var(--text-faint)', border: '1px solid var(--border)' }}
        >
          {finding.confidence === 'high' ? 'high confidence' : `${finding.confidence} confidence`}
        </span>
        <span className="font-mono text-xs ml-auto" style={{ color: 'var(--text-faint)' }}>
          {finding.file_path}:{finding.start_line}
        </span>
        <span
          className="font-mono text-xs px-1.5 py-0.5 rounded"
          style={{ color: 'var(--text-muted)', background: 'var(--surface-raised)' }}
        >
          {finding.function_name}()
        </span>
        <span
          className="font-mono text-xs transition-transform"
          style={{ color: 'var(--text-faint)', transform: expanded ? 'rotate(90deg)' : 'none' }}
        >
          ▸
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-1 space-y-3 border-t" style={{ borderColor: 'var(--border-soft)' }}>
          <pre
            className="font-mono text-xs p-3 rounded overflow-x-auto console-scroll"
            style={{ background: 'var(--bg)', color: 'var(--text)' }}
          >
            {finding.code_snippet}
          </pre>

          <div>
            <div className="font-mono text-[10px] tracking-wider mb-1" style={{ color: 'var(--text-faint)' }}>
              WHY THIS MATTERS
            </div>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--text)' }}>
              {finding.explanation}
            </p>
          </div>

          {finding.suggested_fix && (
            <div>
              <div className="font-mono text-[10px] tracking-wider mb-1" style={{ color: 'var(--sev-safe)' }}>
                SUGGESTED FIX
              </div>
              <p className="text-sm leading-relaxed font-mono" style={{ color: 'var(--text)' }}>
                {finding.suggested_fix}
              </p>
            </div>
          )}

          {finding.context_note && (
            <div
              className="text-xs leading-relaxed rounded px-3 py-2 flex gap-2"
              style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
            >
              <span>↳</span>
              <span>{finding.context_note}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
