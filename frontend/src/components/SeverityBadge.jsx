const SEVERITY_CONFIG = {
  critical: { label: 'CRITICAL', color: 'var(--sev-critical)', bg: 'var(--sev-critical-bg)' },
  high: { label: 'HIGH', color: 'var(--sev-high)', bg: 'var(--sev-high-bg)' },
  medium: { label: 'MEDIUM', color: 'var(--sev-medium)', bg: 'var(--sev-medium-bg)' },
  low: { label: 'LOW', color: 'var(--sev-safe)', bg: 'var(--sev-safe-bg)' },
};

export default function SeverityBadge({ severity, size = 'md' }) {
  const cfg = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.medium;
  const sizeClasses = size === 'sm' ? 'text-[10px] px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      className={`font-mono font-semibold tracking-wider rounded-sm inline-flex items-center gap-1.5 ${sizeClasses}`}
      style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.color}44` }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: cfg.color }} />
      {cfg.label}
    </span>
  );
}

export { SEVERITY_CONFIG };
