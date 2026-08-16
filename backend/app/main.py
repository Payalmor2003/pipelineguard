"""
PipelineGuard FastAPI backend.

Two ways to submit code, both hitting the same analyze_sources() pipeline:
1. Paste code directly (fast path - no cloning, ideal for the live demo,
   since it has no network/clone latency and can't fail on a bad URL).
2. Give a public GitHub repo URL (shallow-cloned into a temp dir, analyzed,
   then deleted - shows the tool works on a real multi-file codebase, not
   just a toy snippet).

Robustness note: the repo path does real network I/O (git clone), local
embedding inference, and an LLM call sized by however many findings the
repo produces - all things that can fail in ways a plain try/except around
just the clone step won't catch. Every route below is wrapped so a failure
anywhere still returns a clean JSON error with CORS headers, instead of the
connection dying mid-request (which surfaces to the browser as an opaque
"Failed to fetch" with no useful detail).
"""

import logging
import tempfile
import traceback
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .agent import analyze_sources
from .ingest import clone_repo, get_file_sources

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipelineguard")

app = FastAPI(title="PipelineGuard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the actual Vercel domain before final submission
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Without this, an unexpected exception anywhere in a route (e.g. a
    # Groq network error, a malformed repo, an out-of-memory embedding
    # batch) can crash the request before FastAPI/CORS get to format a
    # normal response - the browser then reports a bare "Failed to fetch"
    # with no detail. This guarantees every request gets back real JSON
    # (with CORS headers, since this still goes through the middleware
    # stack) even on a genuine bug.
    logger.error("Unhandled exception on %s: %s", request.url.path, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error: {exc}"},
    )


MAX_PASTE_CHARS = 20_000  # keep the free-tier LLM call fast and cheap
MAX_REPO_FILES = 15       # keep clone + embed + one LLM call fast enough for a live demo
MAX_FINDINGS_FOR_LLM = 20  # cap the single explain_findings() call size


class AnalyzeCodeRequest(BaseModel):
    filename: str = Field(default="pasted_code.py")
    code: str


class AnalyzeRepoRequest(BaseModel):
    repo_url: str


class FindingItem(BaseModel):
    rule_id: str
    severity: str
    title: str
    confidence: str
    file_path: str
    start_line: int
    end_line: int
    function_name: str
    code_snippet: str
    explanation: str
    suggested_fix: str
    context_note: str


class AnalyzeResponse(BaseModel):
    summary: str
    findings: list[FindingItem]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze/code", response_model=AnalyzeResponse)
def analyze_code(req: AnalyzeCodeRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty.")
    if len(req.code) > MAX_PASTE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Pasted code exceeds {MAX_PASTE_CHARS} characters. "
                    "Try the repo URL endpoint for larger codebases.",
        )
    filename = req.filename if req.filename.endswith(".py") else f"{req.filename}.py"
    report = analyze_sources({filename: req.code})
    return report


@app.post("/analyze/repo", response_model=AnalyzeResponse)
def analyze_repo_endpoint(req: AnalyzeRepoRequest):
    if not req.repo_url.strip():
        raise HTTPException(status_code=400, detail="repo_url cannot be empty.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "repo"
        try:
            clone_repo(req.repo_url, str(target))
        except Exception as e:
            logger.exception("Clone failed")
            raise HTTPException(status_code=400, detail=f"Could not clone repo: {e}")

        try:
            file_sources = get_file_sources(str(target))
        except Exception as e:
            logger.exception("Reading repo files failed")
            raise HTTPException(status_code=500, detail=f"Could not read repo files: {e}")

        if not file_sources:
            raise HTTPException(
                status_code=400,
                detail="No indexable Python files found in this repo.",
            )
        if len(file_sources) > MAX_REPO_FILES:
            # Narrow initial scope: cap repo size so a live demo call stays
            # fast and the free-tier LLM call doesn't get too large. Larger
            # repos are a "next step" in the product strategy write-up.
            file_sources = dict(list(file_sources.items())[:MAX_REPO_FILES])

        try:
            report = analyze_sources(file_sources, max_findings_for_llm=MAX_FINDINGS_FOR_LLM)
        except Exception as e:
            logger.exception("Analysis failed")
            raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

        return report
