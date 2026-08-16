"""
LangGraph orchestration for PipelineGuard's analysis pipeline.

Why a graph instead of one linear function:
The context-check step needs a fully built retrieval index over the whole
repo, which only makes sense to build once findings exist (no point
indexing/embedding a repo that turned out to have zero findings). The
graph makes this "detect first, then conditionally do the expensive
retrieval-index step" structure explicit, and gives a natural place to add
a future loop (e.g. "explanation confidence low -> pull more context ->
retry") without restructuring the pipeline.

Pipeline: ingest -> detect (deterministic AST rules) -> build_index
          -> context_check (does a safe pattern already exist elsewhere
             in this repo?) -> explain (LLM, narrow scope: explain + fix
             only, never re-decides validity) -> END
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import llm
from .detectors import Finding, detect_repo
from .chunking import Chunk, chunk_file
from .retrieval import HybridIndex

# Search terms used to look up "does this repo already have a safe pattern
# for this?" per rule - kept as a static map rather than derived from the
# finding text, so results are predictable and easy to reason about.
_CONTEXT_QUERIES = {
    "missing_retry": "retry decorator tenacity backoff exception handling",
    "missing_timeout": "timeout parameter request configuration",
    "unbounded_async_batch": "AsyncLimiter semaphore rate limit concurrency",
    "bare_except": "exception logging error handling try except",
    "non_atomic_write": "temp file rename atomic write os.replace",
}


class AgentState(TypedDict):
    file_sources: dict[str, str]
    chunks: list[Chunk]
    findings: list[Finding]
    report: dict
    max_findings_for_llm: int | None


def _ingest_node(state: AgentState) -> AgentState:
    # Chunk directly from the already-read file_sources rather than
    # re-walking disk - file_sources is the single source of truth for
    # both this retrieval-index build and the detectors below, so both
    # stages always see the exact same file content.
    chunks: list[Chunk] = []
    for rel_path, source in state["file_sources"].items():
        if rel_path.endswith(".py"):
            chunks.extend(chunk_file(rel_path, source))
    return {**state, "chunks": chunks}


def _detect_node(state: AgentState) -> AgentState:
    findings = detect_repo(state["file_sources"])
    return {**state, "findings": findings}


def _context_check_and_explain_node(state: AgentState) -> AgentState:
    findings = state["findings"]

    if not findings:
        return {**state, "report": {"findings": [], "summary": "No issues found."}}

    index = None
    if state["chunks"]:
        index = HybridIndex(state["chunks"])

    # Cap how many findings go into a single LLM explain call. A real repo
    # can produce far more findings than a hand-written demo snippet, and
    # stuffing all of them into one prompt risks a truncated/invalid JSON
    # response or hitting the free-tier token limit. We prioritize by
    # severity so the most important findings are the ones that always get
    # a full LLM explanation; the rest still appear in the report with
    # their rule-based detail text as a fallback explanation.
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    max_for_llm = state.get("max_findings_for_llm") or len(findings)
    findings_by_priority = sorted(
        range(len(findings)),
        key=lambda i: severity_order.get(findings[i].severity, 9),
    )
    llm_indices = set(findings_by_priority[:max_for_llm])

    payload = []
    related_snippets: dict[int, str] = {}

    for i, f in enumerate(findings):
        related_snippet = ""
        if index is not None and i in llm_indices:
            query = _CONTEXT_QUERIES.get(f.rule_id, f.title)
            hits = index.search(query, top_k=3)
            # Exclude the finding's own location from its own "related
            # pattern" context - otherwise a missing-retry call would
            # "find itself" as the related snippet, which is meaningless.
            for hit in hits:
                same_spot = (hit.chunk.file_path == f.file_path
                             and hit.chunk.start_line == f.start_line)
                if not same_spot:
                    related_snippet = (
                        f"{hit.chunk.file_path}:{hit.chunk.start_line} "
                        f"({hit.chunk.name}):\n{hit.chunk.content[:300]}"
                    )
                    break
        related_snippets[i] = related_snippet

        if i in llm_indices:
            payload.append({
                "index": i,
                "rule_id": f.rule_id,
                "title": f.title,
                "function_name": f.function_name,
                "code_snippet": f.code_snippet,
                "detail": f.detail,
                "related_snippet": related_snippet,
            })

    try:
        # Batch the LLM call rather than sending all findings at once. A
        # real repo can easily produce 15-20+ findings, and stuffing all of
        # them into one prompt risks the model's response getting
        # truncated at max_tokens mid-JSON, which fails to parse and loses
        # every explanation in the batch - not just the ones that ran over.
        # Smaller batches keep each response comfortably within budget.
        explanations = []
        batch_size = 8
        for start in range(0, len(payload), batch_size):
            batch = payload[start:start + batch_size]
            explanations.extend(llm.explain_findings(batch))
    except Exception:
        # Fail soft: if the LLM call itself errors (network issue, rate
        # limit), still return the report using each finding's rule-based
        # detail text rather than losing the whole analysis.
        explanations = []
    explanation_map = {e["finding_index"]: e for e in explanations}

    enriched = []
    for i, f in enumerate(findings):
        exp = explanation_map.get(i, {})
        enriched.append({
            "rule_id": f.rule_id,
            "severity": f.severity,
            "title": f.title,
            "confidence": f.confidence,
            "file_path": f.file_path,
            "start_line": f.start_line,
            "end_line": f.end_line,
            "function_name": f.function_name,
            "code_snippet": f.code_snippet,
            "explanation": exp.get("explanation", f.detail),
            "suggested_fix": exp.get("suggested_fix", ""),
            "context_note": exp.get("context_note", related_snippets.get(i, "")),
        })

    enriched.sort(key=lambda x: severity_order.get(x["severity"], 9))

    counts = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    summary = f"{len(findings)} issue(s) found: " + ", ".join(
        f"{v} {k}" for k, v in sorted(counts.items(), key=lambda kv: severity_order.get(kv[0], 9))
    )
    if len(findings) > max_for_llm:
        summary += f" (top {max_for_llm} explained in detail by the LLM)"

    return {**state, "report": {"findings": enriched, "summary": summary}}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("ingest", _ingest_node)
    graph.add_node("detect", _detect_node)
    graph.add_node("context_check_and_explain", _context_check_and_explain_node)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "detect")
    graph.add_edge("detect", "context_check_and_explain")
    graph.add_edge("context_check_and_explain", END)

    return graph.compile()


def analyze_sources(file_sources: dict[str, str], max_findings_for_llm: int | None = None) -> dict:
    """file_sources: {relative_file_path: source_text} - works the same
    whether the caller pasted a single file or cloned a full repo."""
    app = build_graph()
    initial_state: AgentState = {
        "file_sources": file_sources,
        "chunks": [],
        "findings": [],
        "report": {},
        "max_findings_for_llm": max_findings_for_llm,
    }
    result = app.invoke(initial_state)
    return result["report"]
