"""
Repository ingestion: clone a repo and chunk every source file.

Design decision - pre-indexed demo repo instead of live arbitrary URLs:
Cloning + embedding an arbitrary repo at request time is slow (can take
minutes for a real-sized repo) and fragile for a live demo. This module
is written generically (works on any local repo path), but the deployed
app runs it once at build/deploy time against a fixed demo repo rather
than on every user request. Supporting arbitrary live repos is listed as
a "next step" in the product strategy write-up.
"""

import os
from pathlib import Path

import git

from .chunking import Chunk, chunk_file

# File extensions we index. Kept intentionally narrow for the demo -
# binary files, images, lockfiles, etc. add noise without retrieval value.
INDEXABLE_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".toml", ".cfg"}

# Directories to skip entirely.
SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv",
             "dist", "build", ".mypy_cache", ".pytest_cache", "egg-info"}


def clone_repo(repo_url: str, dest_dir: str) -> str:
    if os.path.exists(dest_dir) and os.listdir(dest_dir):
        return dest_dir
    # GIT_TERMINAL_PROMPT=0 makes git fail immediately with a clear error
    # instead of hanging indefinitely waiting for a username/password
    # prompt that will never come in a non-interactive server process -
    # this is what happens when someone (accidentally or not) submits a
    # private repo URL.
    # Note: GitPython's kill_after_timeout option is not supported on
    # Windows (it relies on a POSIX-only subprocess feature), so it's
    # deliberately left out here rather than crashing every clone on
    # Windows dev machines.
    git.Repo.clone_from(
        repo_url,
        dest_dir,
        depth=1,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    return dest_dir


def iter_source_files(repo_path: str):
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if Path(fname).suffix in INDEXABLE_EXTENSIONS:
                yield os.path.join(root, fname)


def get_file_sources(repo_path: str) -> dict[str, str]:
    """Walk a local repo checkout and return {relative_path: source_text}
    for every indexable file. Used by both the chunker (for retrieval) and
    the detectors (for static analysis) so both operate on the same file set."""
    sources: dict[str, str] = {}
    for file_path in iter_source_files(repo_path):
        rel_path = os.path.relpath(file_path, repo_path)
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        if source.strip():
            sources[rel_path] = source
    return sources


def ingest_repo(repo_path: str) -> list[Chunk]:
    """Walk a local repo checkout and return chunks for every indexable file."""
    all_chunks: list[Chunk] = []
    for rel_path, source in get_file_sources(repo_path).items():
        all_chunks.extend(chunk_file(rel_path, source))
    return all_chunks
