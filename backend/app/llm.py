"""
LLM client wrapper for Groq's free-tier API (Llama 3.3 70B).

Kept as a thin wrapper (rather than calling groq.Groq() directly all over
the codebase) so the model/provider can be swapped later - e.g. the product
strategy answer proposes an optional paid-provider upgrade path (OpenAI/
Azure) without touching the agent logic.

The LLM's role in PipelineGuard is deliberately narrow: it does NOT decide
whether something is a bug (the AST detectors in detectors.py do that,
deterministically). It only explains findings that a rule has already
flagged and proposes a concrete fix - a much safer, more reliable task to
delegate to an LLM than open-ended bug hunting.
"""

import json
import os

from groq import Groq

MODEL_NAME = "llama-3.3-70b-versatile"

EXPLAIN_SYSTEM_PROMPT = """You are PipelineGuard, a senior reliability engineer \
reviewing findings that a static analyzer already flagged in a Python codebase. \
For each finding you are given the rule that fired, the code snippet, and \
(optionally) a related snippet from elsewhere in the same repo. \
Do not question whether the finding is valid - assume the static analysis is \
correct. Your job is only to: \
1) explain in 1-2 sentences why this is a production risk, in plain language \
2) propose a concrete, minimal code fix (a short snippet or clear instruction) \
3) if a related snippet from elsewhere in the repo was provided and it shows a \
safe pattern already used in this codebase, mention it explicitly and suggest \
reusing that pattern for consistency. \
Respond ONLY with a JSON array, no prose before or after, no markdown code \
fences. Each element: {"finding_index": int, "explanation": str, "suggested_fix": str, "context_note": str}. \
Use an empty string for context_note if no related snippet was given."""


def _get_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to your .env file "
            "(see .env.example)."
        )
    return Groq(api_key=api_key)


def explain_findings(findings_payload: list[dict]) -> list[dict]:
    """findings_payload: list of dicts with keys:
        index, rule_id, title, function_name, code_snippet, detail, related_snippet (optional)
    Returns a list of dicts with: finding_index, explanation, suggested_fix, context_note
    """
    if not findings_payload:
        return []

    client = _get_client()
    user_content = json.dumps(findings_payload, indent=2)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
            {"role": "user", "content": f"Findings:\n{user_content}"},
        ],
        temperature=0.2,
        max_tokens=3000,
    )
    raw = response.choices[0].message.content.strip()

    # Defensive parsing: strip accidental markdown fences even though the
    # prompt asks the model not to include them - free-tier models don't
    # always follow formatting instructions perfectly.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fail soft: return empty explanations rather than crashing the
        # whole analysis run over a formatting hiccup from the LLM.
        return [
            {"finding_index": item["index"], "explanation": "(LLM explanation unavailable)",
             "suggested_fix": "", "context_note": ""}
            for item in findings_payload
        ]
