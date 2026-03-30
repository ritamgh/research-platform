"""Unit tests for orchestrator.nodes.delegate."""
import pytest
from unittest.mock import AsyncMock, patch

from orchestrator.a2a_client import A2ACallError


class TestWebResearchNode:
    @pytest.mark.asyncio
    async def test_returns_web_result_and_retrieved_context_on_success(self):
        from orchestrator.nodes.delegate import web_research_node

        with patch(
            "orchestrator.nodes.delegate.call_agent",
            new=AsyncMock(return_value="web search findings"),
        ):
            result = await web_research_node({"query": "latest AI news"})

        assert result["web_result"] == "web search findings"
        assert result["retrieved_context"] == ["web search findings"]
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_returns_empty_web_result_and_sets_error_on_a2a_error(self):
        from orchestrator.nodes.delegate import web_research_node

        with patch(
            "orchestrator.nodes.delegate.call_agent",
            new=AsyncMock(side_effect=A2ACallError("agent unreachable")),
        ):
            result = await web_research_node({"query": "some query"})

        assert result["web_result"] == ""
        assert "error" in result
        assert "agent unreachable" in result["error"]


class TestRagLookupNode:
    @pytest.mark.asyncio
    async def test_returns_rag_result_and_retrieved_context_on_success(self):
        from orchestrator.nodes.delegate import rag_lookup_node

        with patch(
            "orchestrator.nodes.delegate.call_agent",
            new=AsyncMock(return_value="rag corpus results"),
        ):
            result = await rag_lookup_node({"query": "internal policy"})

        assert result["rag_result"] == "rag corpus results"
        assert result["retrieved_context"] == ["rag corpus results"]
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_returns_empty_rag_result_and_sets_error_on_a2a_error(self):
        from orchestrator.nodes.delegate import rag_lookup_node

        with patch(
            "orchestrator.nodes.delegate.call_agent",
            new=AsyncMock(side_effect=A2ACallError("rag agent timeout")),
        ):
            result = await rag_lookup_node({"query": "some query"})

        assert result["rag_result"] == ""
        assert "error" in result
        assert "rag agent timeout" in result["error"]
