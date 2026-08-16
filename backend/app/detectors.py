"""
PipelineGuard detectors: AST-based static analysis for production
reliability anti-patterns in Python.

Why rule-based AST detection instead of asking an LLM to "find bugs":
LLM-only bug-finding is nondeterministic and easy to fool with irrelevant
code - it will miss things or hallucinate issues depending on prompt
phrasing. Deterministic AST rules give reliable, explainable, reproducible
findings (same input -> same output, every time), which matters for a tool
whose whole point is trustworthy production review. The LLM's job here is
NOT to detect - it's to explain and suggest fixes once a rule has already
fired, which is a much narrower and more reliable thing to ask an LLM to do.

Scope is intentionally narrow (5 rules), and deliberately RELIABILITY-only,
not security. An earlier version included a hardcoded-secret detector, but
that's fundamentally a security concern, not a reliability one, and mixing
the two muddies what this product actually is. It was replaced with
non-atomic file writes, which is a reliability failure mode Payal has
directly built production fixes for (the document-copier / PartMover
tmp-then-rename pattern at Benzeen) - keeping every rule in this file
answerable to the same question: "can this crash or corrupt a production
run?" not "is this a security best practice?"
"""

import ast
from dataclasses import dataclass, field

# Call targets we treat as "external/network calls" for retry & timeout rules.
_HTTP_CALL_ATTRS = {"get", "post", "put", "delete", "patch", "request"}
_HTTP_MODULES = {"requests", "httpx"}
# Chat/completion-style SDK calls (OpenAI/Azure OpenAI client patterns).
_LLM_CALL_ATTRS = {"create"}

# Calls that indicate an atomic rename/move already happened somewhere in
# the function - if present, we assume the write is already being made safe
# and don't flag it, even if we can't prove the rename targets this exact file.
_ATOMIC_RENAME_ATTRS = {"rename", "replace", "move"}

RULES = {
    "missing_retry": {
        "severity": "high",
        "title": "External call without retry protection",
        "confidence": "high",
    },
    "bare_except": {
        "severity": "high",
        "title": "Exception silently swallowed",
        "confidence": "high",
    },
    "missing_timeout": {
        "severity": "medium",
        "title": "Network call without explicit timeout",
        "confidence": "high",
    },
    "unbounded_async_batch": {
        "severity": "high",
        "title": "Unbounded concurrent async batch",
        "confidence": "high",
    },
    "non_atomic_write": {
        "severity": "medium",
        "title": "Non-atomic file write",
        # Lower confidence than the other rules: this one relies on a
        # heuristic (does the function contain a rename/move call anywhere,
        # does the path look like a temp file) rather than a structural
        # guarantee, so it's more prone to a false positive/negative than
        # e.g. missing_retry, which is a direct structural check.
        "confidence": "medium",
    },
}


@dataclass
class Finding:
    rule_id: str
    severity: str
    title: str
    confidence: str
    file_path: str
    start_line: int
    end_line: int
    function_name: str
    code_snippet: str
    detail: str
    explanation: str = ""
    suggested_fix: str = ""
    context_note: str = ""


def _snippet(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1:end])


def _is_http_call(node: ast.Call) -> bool:
    """True only for calls that plausibly hit the network: a direct
    requests/httpx module call, or a call on a receiver whose name suggests
    an HTTP client/session object.

    A bare `.get()`/`.post()` on ANY object (a dict, a queue, a custom
    class) is common Python and must NOT be flagged - matching any `.get()`
    call regardless of receiver produces false positives like
    `item.get("group", "UNKNOWN")` on a plain dict. Precision matters more
    than recall for a tool that's supposed to be trusted, so this is
    deliberately conservative.
    """
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in _HTTP_CALL_ATTRS:
        return False

    receiver = func.value
    if isinstance(receiver, ast.Name):
        if receiver.id in _HTTP_MODULES:
            return True
        return any(hint in receiver.id.lower() for hint in ("session", "client", "http"))
    if isinstance(receiver, ast.Attribute):
        return any(hint in receiver.attr.lower() for hint in ("session", "client", "http"))
    return False


def _is_llm_sdk_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _LLM_CALL_ATTRS:
        # crude but effective: .create( on a chain that mentions chat/completions/images
        chain = ast.dump(func)
        if any(kw in chain for kw in ("chat", "completions", "images", "embeddings")):
            return True
    return False


def _has_timeout_kwarg(node: ast.Call) -> bool:
    return any(kw.arg == "timeout" for kw in node.keywords)


def _enclosing_function_has_retry_decorator(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in func_node.decorator_list:
        dec_src = ast.dump(dec)
        if "retry" in dec_src.lower():
            return True
    return False


def _call_wrapped_in_try(call_node: ast.Call, func_node: ast.AST) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if child is call_node:
                    return True
    return False


def _except_is_swallowed(handler: ast.ExceptHandler) -> bool:
    """A handler is 'swallowed' if its body is just `pass`, or contains no
    logging call and no re-raise. This intentionally has false-negative bias
    (better to under-flag than spam every except block)."""
    if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
        return True
    has_raise = any(isinstance(n, ast.Raise) for n in handler.body)
    has_log_call = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"error", "exception", "warning", "critical", "log"}
        for n in ast.walk(ast.Module(body=handler.body, type_ignores=[]))
    )
    return not has_raise and not has_log_call


def _is_bare_or_broad_except(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
        return True
    return False


def _has_rate_limiter_in_scope(func_node: ast.AST) -> bool:
    src = ast.dump(func_node)
    return any(term in src for term in ("Semaphore", "AsyncLimiter", "RateLimiter", "limiter"))


def _is_open_write_call(node: ast.Call) -> str | None:
    """Returns the file mode string if this is a call to builtin open() in
    a write mode ('w', 'wb', 'a', etc.), else None."""
    if not (isinstance(node.func, ast.Name) and node.func.id == "open"):
        return None
    mode = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        mode = node.args[1].value
    else:
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
    if mode and "w" in mode:
        return mode
    return None


def _open_path_arg(node: ast.Call) -> ast.AST | None:
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg == "file":
            return kw.value
    return None


def _path_looks_temporary(path_node: ast.AST) -> bool:
    """Heuristic: does the path expression look like it's already a temp
    file (about to be renamed into place), so this open() itself is fine?"""
    if isinstance(path_node, ast.Constant) and isinstance(path_node.value, str):
        return "tmp" in path_node.value.lower()
    if isinstance(path_node, ast.Name):
        return "tmp" in path_node.id.lower() or "temp" in path_node.id.lower()
    if isinstance(path_node, ast.JoinedStr):  # f-string
        for value in path_node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and "tmp" in value.value.lower():
                return True
    return False


def _function_has_atomic_rename(func_node: ast.AST) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in _ATOMIC_RENAME_ATTRS:
            return True
    return False


def detect_findings(file_path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    lines = source.splitlines()

    for func_node in ast.walk(tree):
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        has_retry_decorator = _enclosing_function_has_retry_decorator(func_node)
        has_atomic_rename = _function_has_atomic_rename(func_node)

        for node in ast.walk(func_node):
            # --- Rule: missing_retry ---
            if isinstance(node, ast.Call) and (_is_http_call(node) or _is_llm_sdk_call(node)):
                wrapped = _call_wrapped_in_try(node, func_node)
                if not wrapped and not has_retry_decorator:
                    findings.append(Finding(
                        rule_id="missing_retry",
                        severity=RULES["missing_retry"]["severity"],
                        title=RULES["missing_retry"]["title"],
                        confidence=RULES["missing_retry"]["confidence"],
                        file_path=file_path,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        function_name=func_node.name,
                        code_snippet=_snippet(lines, node.lineno, getattr(node, "end_lineno", node.lineno)),
                        detail=(
                            f"Call in `{func_node.name}` has no surrounding try/except "
                            "and the function has no retry decorator. A transient "
                            "network blip or a rate-limit response will crash the "
                            "whole run instead of being retried."
                        ),
                    ))

                # --- Rule: missing_timeout ---
                if _is_http_call(node) and not _has_timeout_kwarg(node):
                    findings.append(Finding(
                        rule_id="missing_timeout",
                        severity=RULES["missing_timeout"]["severity"],
                        title=RULES["missing_timeout"]["title"],
                        confidence=RULES["missing_timeout"]["confidence"],
                        file_path=file_path,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        function_name=func_node.name,
                        code_snippet=_snippet(lines, node.lineno, getattr(node, "end_lineno", node.lineno)),
                        detail=(
                            "No `timeout=` passed. Without it, a hung connection can "
                            "block this call indefinitely instead of failing fast."
                        ),
                    ))

            # --- Rule: bare_except ---
            if isinstance(node, ast.ExceptHandler) and _is_bare_or_broad_except(node) \
                    and _except_is_swallowed(node):
                end_line = getattr(node, "end_lineno", node.lineno)
                findings.append(Finding(
                    rule_id="bare_except",
                    severity=RULES["bare_except"]["severity"],
                    title=RULES["bare_except"]["title"],
                    confidence=RULES["bare_except"]["confidence"],
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=end_line,
                    function_name=func_node.name,
                    code_snippet=_snippet(lines, node.lineno, end_line),
                    detail=(
                        f"In `{func_node.name}`, this except block catches broadly and "
                        "neither logs nor re-raises. The failure disappears silently, "
                        "which makes production issues nearly impossible to diagnose later."
                    ),
                ))

            # --- Rule: unbounded_async_batch ---
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "gather" \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "asyncio":
                if not _has_rate_limiter_in_scope(func_node):
                    end_line = getattr(node, "end_lineno", node.lineno)
                    findings.append(Finding(
                        rule_id="unbounded_async_batch",
                        severity=RULES["unbounded_async_batch"]["severity"],
                        title=RULES["unbounded_async_batch"]["title"],
                        confidence=RULES["unbounded_async_batch"]["confidence"],
                        file_path=file_path,
                        start_line=node.lineno,
                        end_line=end_line,
                        function_name=func_node.name,
                        code_snippet=_snippet(lines, node.lineno, end_line),
                        detail=(
                            f"`asyncio.gather` in `{func_node.name}` runs all tasks "
                            "concurrently with no Semaphore/AsyncLimiter in scope. On a "
                            "large batch this can blow through an API's rate limit all at once."
                        ),
                    ))

            # --- Rule: non_atomic_write ---
            if isinstance(node, ast.Call):
                mode = _is_open_write_call(node)
                if mode is not None:
                    path_node = _open_path_arg(node)
                    is_temp_path = path_node is not None and _path_looks_temporary(path_node)
                    if not is_temp_path and not has_atomic_rename:
                        end_line = getattr(node, "end_lineno", node.lineno)
                        findings.append(Finding(
                            rule_id="non_atomic_write",
                            severity=RULES["non_atomic_write"]["severity"],
                            title=RULES["non_atomic_write"]["title"],
                            confidence=RULES["non_atomic_write"]["confidence"],
                            file_path=file_path,
                            start_line=node.lineno,
                            end_line=end_line,
                            function_name=func_node.name,
                            code_snippet=_snippet(lines, node.lineno, end_line),
                            detail=(
                                f"`{func_node.name}` writes directly to its target path "
                                f"(mode `{mode}`) with no temp-file-then-rename pattern "
                                "detected in this function. If the process crashes or is "
                                "killed mid-write, a reader can see a truncated or "
                                "corrupted file instead of the old or new version."
                            ),
                        ))

    return findings


def detect_repo(file_sources: dict[str, str]) -> list[Finding]:
    """file_sources: {relative_file_path: source_text}"""
    all_findings: list[Finding] = []
    for path, source in file_sources.items():
        if path.endswith(".py"):
            all_findings.extend(detect_findings(path, source))
    return all_findings
