const DEMO_LINES = [
  { text: 'import requests', dot: null },
  { text: '', dot: null },
  { text: 'def fetch_data(url):', dot: null },
  { text: '    return requests.get(url)', dot: 'high' },
  { text: '', dot: null },
  { text: 'def save(path, data):', dot: null },
  { text: '    with open(path, "w") as f:', dot: 'medium' },
  { text: '        f.write(data)', dot: null },
  { text: '', dot: null },
  { text: 'def parse(raw):', dot: null },
  { text: '    try:', dot: null },
  { text: '        return int(raw)', dot: null },
  { text: '    except:', dot: 'high' },
  { text: '        pass', dot: null },
];

const DOT_STYLE = {
  critical: 'var(--sev-critical)',
  high: 'var(--sev-high)',
  medium: 'var(--sev-medium)',
};

export default function ScanHero() {
  const lineCount = DEMO_LINES.length;
  const sweepDuration = 4.5; // must match .animate-scan in index.css

  return (
    <div
      className="relative rounded-lg border overflow-hidden"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      aria-hidden="true"
    >
      {/* Terminal chrome */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 border-b"
        style={{ borderColor: 'var(--border)' }}
      >
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#5B5F69' }} />
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#5B5F69' }} />
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#5B5F69' }} />
        <span className="font-mono text-xs ml-2" style={{ color: 'var(--text-faint)' }}>
          pipeline.py — scanning
        </span>
      </div>

      <div className="relative px-5 py-5 font-mono text-[13px] leading-6">
        {/* Sweeping scan beam */}
        <div
          className="animate-scan absolute left-0 right-0 h-10 pointer-events-none"
          style={{
            top: 0,
            background: 'linear-gradient(to bottom, transparent, var(--accent-soft) 45%, var(--accent-soft) 55%, transparent)',
          }}
        />

        {DEMO_LINES.map((line, i) => (
          <div key={i} className="relative flex items-center gap-3">
            <span
              className="w-4 text-right select-none flex-shrink-0"
              style={{ color: 'var(--text-faint)' }}
            >
              {i + 1}
            </span>

            {/* Gutter dot, timed to pop as the beam passes this line */}
            <span className="w-2.5 flex-shrink-0 flex justify-center">
              {line.dot && (
                <span
                  className="w-2 h-2 rounded-full animate-dot-pop"
                  style={{
                    background: DOT_STYLE[line.dot],
                    opacity: 0,
                    animationDelay: `${(i / lineCount) * sweepDuration + 0.15}s`,
                    animationDuration: `${sweepDuration}s`,
                    animationIterationCount: 'infinite',
                  }}
                />
              )}
            </span>

            <span style={{ color: line.text.trim().startsWith('#') ? 'var(--text-faint)' : 'var(--text)' }}>
              {line.text || '\u00A0'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
