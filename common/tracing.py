"""Shared tracing utilities for cross-service LangSmith trace propagation.

Embeds LangSmith trace headers (trace_id, parent_run_id) into query strings so
they survive the A2A / ADK message boundary.  Each agent extracts the context
and wraps its work in ``tracing_context(parent=headers)`` so its runs appear as
children of the orchestrator's ``research_pipeline`` trace.
"""

import base64
import json
import re

from langsmith.run_helpers import get_current_run_tree, tracing_context

# ── wire format ──────────────────────────────────────────────────────────────
_MARKER = "__LST__"
_TRACE_RE = re.compile(
    rf"^{re.escape(_MARKER)}([A-Za-z0-9+/=\-]+){re.escape(_MARKER)}"
)


def get_trace_headers() -> dict:
    """Return LangSmith trace headers from the current run (empty dict if none)."""
    run = get_current_run_tree()
    return run.to_headers() if run else {}


def encode_trace_context(headers: dict) -> str:
    """Encode trace headers into a compact prefix string."""
    if not headers:
        return ""
    payload = base64.b64encode(json.dumps(headers).encode()).decode()
    return f"{_MARKER}{payload}{_MARKER}"


def inject_trace(text: str, headers: dict) -> str:
    """Prepend encoded trace context to *text*."""
    prefix = encode_trace_context(headers)
    return f"{prefix}{text}" if prefix else text


def extract_trace(text: str) -> tuple[dict | None, str]:
    """Strip encoded trace context from *text*.

    Returns (headers_dict_or_None, cleaned_text).
    """
    m = _TRACE_RE.match(text)
    if not m:
        return None, text
    try:
        headers = json.loads(base64.b64decode(m.group(1)).decode())
        return headers, text[m.end():]
    except Exception:
        return None, text


def child_span(name: str, headers: dict | None):
    """Context manager that creates a child span under the propagated trace.

    Usage::

        headers, clean_q = extract_trace(query)
        with child_span("rag_lookup", headers):
            result = await run_rag_lookup(clean_q)
    """
    if headers:
        return tracing_context(parent=headers)
    from contextlib import nullcontext
    return nullcontext()
