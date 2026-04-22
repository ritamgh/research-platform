"""Unit tests for common.tracing — LangSmith trace context propagation."""
import pytest

from common.tracing import encode_trace_context, inject_trace, extract_trace


class TestEncodeTraceContext:
    def test_encodes_non_empty_headers(self):
        result = encode_trace_context({"langsmith-trace": "abc"})
        assert result.startswith("__LST__")
        assert result.endswith("__LST__")

    def test_returns_empty_for_empty_headers(self):
        assert encode_trace_context({}) == ""
        assert encode_trace_context(None) == ""


class TestInjectTrace:
    def test_prepends_context(self):
        headers = {"langsmith-trace": "t1", "langsmith-parent": "p1"}
        result = inject_trace("hello world", headers)
        assert result.endswith("hello world")
        assert result != "hello world"

    def test_passthrough_when_no_headers(self):
        assert inject_trace("hello", {}) == "hello"
        assert inject_trace("hello", None) == "hello"


class TestExtractTrace:
    def test_roundtrip(self):
        headers = {"langsmith-trace": "trace-123", "langsmith-parent": "parent-456"}
        marked = inject_trace("What are transformers?", headers)
        extracted, clean = extract_trace(marked)
        assert extracted == headers
        assert clean == "What are transformers?"

    def test_no_prefix(self):
        extracted, clean = extract_trace("plain query")
        assert extracted is None
        assert clean == "plain query"

    def test_empty_string(self):
        extracted, clean = extract_trace("")
        assert extracted is None
        assert clean == ""

    def test_malformed_prefix_returns_original(self):
        text = "__LST__not-valid-base64!!!__LST__rest"
        extracted, clean = extract_trace(text)
        assert extracted is None
        assert clean == text

    def test_preserves_special_chars_in_query(self):
        headers = {"langsmith-trace": "t"}
        marked = inject_trace("What is RAG? [CONFIDENCE: HIGH]\n<rag_sources>src1</rag_sources>", headers)
        extracted, clean = extract_trace(marked)
        assert extracted == headers
        assert clean == "What is RAG? [CONFIDENCE: HIGH]\n<rag_sources>src1</rag_sources>"
