"""Unit tests for orchestrator.nodes.router."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestRouterNode:
    @pytest.mark.asyncio
    async def test_returns_web_only_route(self):
        from orchestrator.nodes.router import router_node

        mock_response = MagicMock()
        mock_response.content = '{"route": "web_only", "reasoning": "needs current news"}'

        with patch("orchestrator.nodes.router.ChatAnthropic") as MockLLM:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance

            result = await router_node({"query": "What are the latest AI news?"})

        assert result == {"route": "web_only"}

    @pytest.mark.asyncio
    async def test_returns_rag_only_route(self):
        from orchestrator.nodes.router import router_node

        mock_response = MagicMock()
        mock_response.content = '{"route": "rag_only", "reasoning": "stored docs"}'

        with patch("orchestrator.nodes.router.ChatAnthropic") as MockLLM:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance

            result = await router_node({"query": "What does the internal policy say?"})

        assert result == {"route": "rag_only"}

    @pytest.mark.asyncio
    async def test_returns_both_route(self):
        from orchestrator.nodes.router import router_node

        mock_response = MagicMock()
        mock_response.content = '{"route": "both", "reasoning": "benefits from both"}'

        with patch("orchestrator.nodes.router.ChatAnthropic") as MockLLM:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance

            result = await router_node({"query": "Compare recent papers with our corpus"})

        assert result == {"route": "both"}

    @pytest.mark.asyncio
    async def test_falls_back_to_both_on_invalid_json(self):
        from orchestrator.nodes.router import router_node

        mock_response = MagicMock()
        mock_response.content = "this is not valid JSON at all"

        with patch("orchestrator.nodes.router.ChatAnthropic") as MockLLM:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance

            result = await router_node({"query": "some query"})

        assert result == {"route": "both"}

    @pytest.mark.asyncio
    async def test_falls_back_to_both_on_llm_exception(self):
        from orchestrator.nodes.router import router_node

        with patch("orchestrator.nodes.router.ChatAnthropic") as MockLLM:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.ainvoke = AsyncMock(
                side_effect=RuntimeError("LLM connection error")
            )
            MockLLM.return_value = mock_llm_instance

            result = await router_node({"query": "some query that causes LLM error"})

        assert result == {"route": "both"}

    @pytest.mark.asyncio
    async def test_returns_both_for_empty_query_without_llm_call(self):
        from orchestrator.nodes.router import router_node

        with patch("orchestrator.nodes.router.ChatAnthropic") as MockLLM:
            result = await router_node({"query": ""})

        # LLM should NOT have been instantiated
        MockLLM.assert_not_called()
        assert result == {"route": "both"}

    @pytest.mark.asyncio
    async def test_falls_back_to_both_for_unknown_route_value(self):
        from orchestrator.nodes.router import router_node

        mock_response = MagicMock()
        mock_response.content = '{"route": "unknown_category", "reasoning": "oops"}'

        with patch("orchestrator.nodes.router.ChatAnthropic") as MockLLM:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance

            result = await router_node({"query": "ambiguous query"})

        assert result == {"route": "both"}
