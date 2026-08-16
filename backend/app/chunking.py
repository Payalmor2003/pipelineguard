"""
Chunking strategy for RepoMind.

Why AST-based chunking instead of fixed-size line windows:
Fixed-size chunking (e.g. every 50 lines) frequently cuts a function or class
in half. A retrieval hit on half a function is close to useless to both a
human and an LLM, because the chunk has no coherent standalone meaning.

For Python files we parse the AST and chunk at function/class boundaries, so
every chunk is a complete, semantically meaningful unit. For non-Python files
(or Python files that fail to parse, e.g. syntax errors in a WIP branch), we
fall back to a sliding line-window so ingestion never hard-fails on a repo.
"""

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    kind: str  # "function" | "class" | "module" | "window"
    name: str
    content: str
    metadata: dict = field(default_factory=dict)


def _make_id(file_path: str, start_line: int, end_line: int) -> str:
    raw = f"{file_path}:{start_line}-{end_line}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def chunk_python_file(file_path: str, source: str) -> list[Chunk]:
    """AST-based chunking for a single Python file.

    Falls back to chunk_generic_file if the source fails to parse
    (e.g. Python 2 syntax, a WIP file with a syntax error).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return chunk_generic_file(file_path, source)

    lines = source.splitlines()
    chunks: list[Chunk] = []
    top_level_nodes = [
        n for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]

    if not top_level_nodes:
        # No functions/classes at top level (e.g. a config/constants file) -
        # treat the whole file as one module-level chunk.
        return chunk_generic_file(file_path, source)

    for node in top_level_nodes:
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        content = "\n".join(lines[start - 1:end])
        kind = "class" if isinstance(node, ast.ClassDef) else "function"

        chunks.append(Chunk(
            chunk_id=_make_id(file_path, start, end),
            file_path=file_path,
            start_line=start,
            end_line=end,
            kind=kind,
            name=node.name,
            content=content,
            metadata={"docstring": ast.get_docstring(node) or ""},
        ))

        # For classes, also index each method as its own chunk, since a
        # question like "how does X handle retries" usually targets one
        # method, not the whole class body.
        if isinstance(node, ast.ClassDef):
            for sub in ast.iter_child_nodes(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_start = sub.lineno
                    m_end = getattr(sub, "end_lineno", m_start)
                    m_content = "\n".join(lines[m_start - 1:m_end])
                    chunks.append(Chunk(
                        chunk_id=_make_id(file_path, m_start, m_end),
                        file_path=file_path,
                        start_line=m_start,
                        end_line=m_end,
                        kind="function",
                        name=f"{node.name}.{sub.name}",
                        content=m_content,
                        metadata={"docstring": ast.get_docstring(sub) or "",
                                  "parent_class": node.name},
                    ))

    return chunks


def chunk_generic_file(file_path: str, source: str, window_lines: int = 60,
                        overlap: int = 10) -> list[Chunk]:
    """Sliding-window fallback for non-Python files or unparseable source."""
    lines = source.splitlines()
    if not lines:
        return []

    chunks: list[Chunk] = []
    step = max(window_lines - overlap, 1)
    for start in range(0, len(lines), step):
        end = min(start + window_lines, len(lines))
        content = "\n".join(lines[start:end])
        if not content.strip():
            continue
        chunks.append(Chunk(
            chunk_id=_make_id(file_path, start + 1, end),
            file_path=file_path,
            start_line=start + 1,
            end_line=end,
            kind="window",
            name=Path(file_path).name,
            content=content,
        ))
        if end == len(lines):
            break

    return chunks


def chunk_file(file_path: str, source: str) -> list[Chunk]:
    """Entry point: routes to AST or generic chunking by extension."""
    if file_path.endswith(".py"):
        return chunk_python_file(file_path, source)
    return chunk_generic_file(file_path, source)
