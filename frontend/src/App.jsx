import ScanHero from "./components/ScanHero";
import PipelineStages from "./components/PipelineStages";
import AnalyzePanel from "./components/AnalyzePanel";

const RULES = [
  {
    name: "Missing retry",
    desc: "External calls with no retry/backoff",
    severity: "high",
  },
  {
    name: "Missing timeout",
    desc: "Network calls that can hang forever",
    severity: "medium",
  },
  {
    name: "Swallowed exceptions",
    desc: "Bare except blocks that hide failures",
    severity: "high",
  },
  {
    name: "Unbounded async batch",
    desc: "Concurrent calls with no rate limit",
    severity: "high",
  },
  {
    name: "Non-atomic write",
    desc: "Potentially unsafe direct writes without atomic replacement",
    severity: "medium",
  },
];

const SEVERITY_COLORS = {
  critical: "var(--sev-critical)",
  high: "var(--sev-high)",
  medium: "var(--sev-medium)",
  low: "var(--sev-safe)",
};

function Nav() {
  return (
    <nav className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <div
          className="w-2 h-2 rounded-full"
          style={{ background: "var(--sev-safe)" }}
        />
        <span className="font-display font-semibold text-sm tracking-tight">
          PipelineGuard
        </span>
      </div>
      <a
        href="#analyze"
        className="font-mono text-xs px-3 py-1.5 rounded border transition-colors"
        style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
      >
        try it →
      </a>
    </nav>
  );
}

function Hero() {
  return (
    <header className="bg-grid">
      <div className="max-w-5xl mx-auto px-6 pt-10 pb-16 grid md:grid-cols-2 gap-10 items-center">
        <div>
          <div
            className="font-mono text-xs mb-4 inline-flex items-center gap-2 px-2.5 py-1 rounded"
            style={{
              background: "var(--surface)",
              color: "var(--text-muted)",
              border: "1px solid var(--border)",
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: "var(--accent)" }}
            />
            production reliability agent
          </div>
          <h1 className="font-display font-bold text-4xl sm:text-5xl leading-[1.1] mb-5">
            Your code works.
            <br />
            <span style={{ color: "var(--accent)" }}>Will it survive</span>
            <br />
            production?
          </h1>
          <p
            className="text-base leading-relaxed mb-7 max-w-md"
            style={{ color: "var(--text-muted)" }}
          >
            PipelineGuard reviews Python pipelines for the failure modes that
            don't show up in tests — missing retries, silent exceptions,
            unbounded batches, unsafe file writes — and explains exactly why
            each one matters before it pages you at 2am.
          </p>
          <a
            href="#analyze"
            className="font-mono text-sm px-5 py-3 rounded font-medium inline-block transition-opacity hover:opacity-90"
            style={{ background: "var(--accent)", color: "var(--accent-text)" }}
          >
            ▸ scan your code
          </a>
        </div>

        <ScanHero />
      </div>
    </header>
  );
}

function RulesStrip() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-10">
      <div
        className="font-mono text-xs mb-4"
        style={{ color: "var(--text-faint)" }}
      >
        WHAT IT CATCHES · v1 scope, narrow by design
      </div>
      <div className="grid sm:grid-cols-2 md:grid-cols-5 gap-3">
        {RULES.map((rule) => (
          <div
            key={rule.name}
            className="rounded-md border p-3.5"
            style={{
              background: "var(--surface)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex items-center justify-between mb-1">
              <div className="font-display text-sm font-medium">
                {rule.name}
              </div>
              <span
                className="font-mono text-[9px] tracking-wide"
                style={{ color: SEVERITY_COLORS[rule.severity] }}
              >
                {rule.severity.toUpperCase()}
              </span>
            </div>
            <div
              className="text-xs leading-snug"
              style={{ color: "var(--text-muted)" }}
            >
              {rule.desc}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-10">
      <div
        className="font-mono text-xs mb-4"
        style={{ color: "var(--text-faint)" }}
      >
        HOW A SCAN RUNS
      </div>
      <PipelineStages />
    </section>
  );
}

function AnalyzeSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-10">
      <div
        className="font-mono text-xs mb-4"
        style={{ color: "var(--text-faint)" }}
      >
        RUN IT
      </div>
      <AnalyzePanel />
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t mt-10" style={{ borderColor: "var(--border)" }}>
      <div className="max-w-5xl mx-auto px-6 py-8 flex flex-col sm:flex-row justify-between gap-3">
        <span
          className="font-mono text-xs"
          style={{ color: "var(--text-faint)" }}
        >
          PipelineGuard — pasted code is analyzed in memory. Repo clones are
          temporary and deleted immediately after analysis.
        </span>
        <span
          className="font-mono text-xs"
          style={{ color: "var(--text-faint)" }}
        >
          built by Payal Mor
        </span>
      </div>
    </footer>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <Nav />
      <Hero />
      <RulesStrip />
      <HowItWorks />
      <AnalyzeSection />
      <Footer />
    </div>
  );
}
