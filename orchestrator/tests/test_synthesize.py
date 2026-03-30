"""Unit tests for orchestrator.nodes.synthesize."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.a2a_client import A2ACallError


class TestSynthesizeNode:
    @pytest.mark.asyncio
    async def test_calls_summariser_with_correct_json_payload(self):
        from orchestrator.nodes.synthesize import synthesize_node

        captured_payloads: list[str] = []

        async def mock_call_agent(url: str, payload: str, timeout: float) -> str:
            captured_payloads.append(payload)
            return "final synthesized answer"

        state = {
            "query": "What is RAG?",
            "route": "both",
            "web_result": "web findings about RAG",
            "rag_result": "rag corpus results about RAG",
        }

        with patch(
            "orchestrator.nodes.synthesize.call_agent",
            new=mock_call_agent,
        ):
            await synthesize_node(state)

        assert len(captured_payloads) == 1
        parsed = json.loads(captured_payloads[0])
        assert parsed["query"] == "What is RAG?"
        assert parsed["web_findings"] == "web findings about RAG"
        assert parsed["rag_findings"] == "rag corpus results about RAG"

    @pytest.mark.asyncio
    async def test_returns_final_answer_with_extracted_sources(self):
        from orchestrator.nodes.synthesize import synthesize_node

        answer_with_sources = (
            "RAG combines retrieval with generation. "
            "See https://arxiv.org/abs/2005.11401 for details."
        )

        state = {
            "query": "What is RAG?",
            "route": "both",
            "web_result": "some web result",
            "rag_result": "some rag result",
        }

        with patch(
            "orchestrator.nodes.synthesize.call_agent",
            new=AsyncMock(return_value=answer_with_sources),
        ):
            result = await synthesize_node(state)

        assert result["final_answer"] == answer_with_sources
        assert "https://arxiv.org/abs/2005.11401" in result["sources"]

    @pytest.mark.asyncio
    async def test_uses_llm_directly_for_direct_route(self):
        from orchestrator.nodes.synthesize import synthesize_node

        mock_response = MagicMock()
        mock_response.content = "42 is the answer."

        state = {
            "query": "What is 6 times 7?",
            "route": "direct",
            "web_result": "",
            "rag_result": "",
        }

        with patch("orchestrator.nodes.synthesize.call_agent") as mock_call_agent, patch(
            "orchestrator.nodes.synthesize.ChatAnthropic"
        ) as MockLLM:
            mock_llm_instance = MagicMock()
            mock_llm_instance.invoke = MagicMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance

            result = await synthesize_node(state)

        # summariser should NOT be called for direct route
        mock_call_agent.assert_not_called()
        assert result["final_answer"] == "42 is the answer."

    @pytest.mark.asyncio
    async def test_falls_back_to_combining_results_on_a2a_call_error(self):
        from orchestrator.nodes.synthesize import synthesize_node

        state = {
            "query": "some query",
            "route": "both",
            "web_result": "web findings",
            "rag_result": "rag findings",
        }

        with patch(
            "orchestrator.nodes.synthesize.call_agent",
            new=AsyncMock(side_effect=A2ACallError("summariser down")),
        ):
            result = await synthesize_node(state)

        assert "web findings" in result["final_answer"]
        assert "rag findings" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_falls_back_gracefully_when_both_results_empty_on_error(self):
        from orchestrator.nodes.synthesize import synthesize_node

        state = {
            "query": "some query",
            "route": "both",
            "web_result": "",
            "rag_result": "",
        }

        with patch(
            "orchestrator.nodes.synthesize.call_agent",
            new=AsyncMock(side_effect=A2ACallError("summariser crashed")),
        ):
            result = await synthesize_node(state)

        # Should return error message rather than crash
        assert "final_answer" in result
        assert len(result["final_answer"]) > 0
