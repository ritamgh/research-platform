"""Unit tests for orchestrator.graph — wiring and routing logic."""
import pytest
from unittest.mock import patch


class TestBuildGraph:
    def test_graph_compiles_without_error(self):
        from orchestrator.graph import build_graph

        graph = build_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        from orchestrator.graph import build_graph
        from langgraph.graph.state import CompiledStateGraph

        graph = build_graph()
        assert isinstance(graph, CompiledStateGraph)


class TestGraphRouting:
    """Test that correct nodes are invoked for each route.

    Patches are applied to orchestrator.graph where the node functions are
    imported — this ensures the compiled graph uses the mocked callables.
    """

    @pytest.mark.asyncio
    async def test_web_only_route_calls_web_research_not_rag(self):
        web_called = []
        rag_called = []

        async def mock_router(state):
            return {"route": "web_only"}

        async def mock_web_research(state):
            web_called.append(state.get("query"))
            return {"web_result": "web answer", "retrieved_context": ["web answer"]}

        async def mock_rag_lookup(state):
            rag_called.append(state.get("query"))
            return {"rag_result": "rag answer", "retrieved_context": ["rag answer"]}

        async def mock_synthesize(state):
            return {"final_answer": "web only answer", "sources": []}

        with (
            patch("orchestrator.graph.router_node", mock_router),
            patch("orchestrator.graph.web_research_node", mock_web_research),
            patch("orchestrator.graph.rag_lookup_node", mock_rag_lookup),
            patch("orchestrator.graph.synthesize_node", mock_synthesize),
        ):
            from orchestrator.graph import build_graph

            graph = build_graph()
            result = await graph.ainvoke({"query": "latest news"})

        assert len(web_called) == 1
        assert len(rag_called) == 0
        assert result["final_answer"] == "web only answer"

    @pytest.mark.asyncio
    async def test_rag_only_route_calls_rag_not_web_research(self):
        web_called = []
        rag_called = []

        async def mock_router(state):
            return {"route": "rag_only"}

        async def mock_web_research(state):
            web_called.append(state.get("query"))
            return {"web_result": "web answer", "retrieved_context": ["web answer"]}

        async def mock_rag_lookup(state):
            rag_called.append(state.get("query"))
            return {"rag_result": "rag answer", "retrieved_context": ["rag answer"]}

        async def mock_synthesize(state):
            return {"final_answer": "rag only answer", "sources": []}

        with (
            patch("orchestrator.graph.router_node", mock_router),
            patch("orchestrator.graph.web_research_node", mock_web_research),
            patch("orchestrator.graph.rag_lookup_node", mock_rag_lookup),
            patch("orchestrator.graph.synthesize_node", mock_synthesize),
        ):
            from orchestrator.graph import build_graph

            graph = build_graph()
            result = await graph.ainvoke({"query": "policy document"})

        assert len(web_called) == 0
        assert len(rag_called) == 1
        assert result["final_answer"] == "rag only answer"

    @pytest.mark.asyncio
    async def test_both_route_calls_web_research_then_rag_then_synthesize(self):
        call_order = []

        async def mock_router(state):
            return {"route": "both"}

        async def mock_web_research(state):
            call_order.append("web_research")
            return {"web_result": "web answer", "retrieved_context": ["web answer"]}

        async def mock_rag_lookup(state):
            call_order.append("rag_lookup")
            return {"rag_result": "rag answer", "retrieved_context": ["rag answer"]}

        async def mock_synthesize(state):
            call_order.append("synthesize")
            return {"final_answer": "combined answer", "sources": []}

        with (
            patch("orchestrator.graph.router_node", mock_router),
            patch("orchestrator.graph.web_research_node", mock_web_research),
            patch("orchestrator.graph.rag_lookup_node", mock_rag_lookup),
            patch("orchestrator.graph.synthesize_node", mock_synthesize),
        ):
            from orchestrator.graph import build_graph

            graph = build_graph()
            result = await graph.ainvoke({"query": "comprehensive research"})

        assert call_order == ["web_research", "rag_lookup", "synthesize"]
        assert result["final_answer"] == "combined answer"

    @pytest.mark.asyncio
    async def test_direct_route_skips_delegate_nodes(self):
        web_called = []
        rag_called = []

        async def mock_router(state):
            return {"route": "direct"}

        async def mock_web_research(state):
            web_called.append(True)
            return {"web_result": "web answer", "retrieved_context": ["web answer"]}

        async def mock_rag_lookup(state):
            rag_called.append(True)
            return {"rag_result": "rag answer", "retrieved_context": ["rag answer"]}

        async def mock_synthesize(state):
            return {"final_answer": "direct answer", "sources": []}

        with (
            patch("orchestrator.graph.router_node", mock_router),
            patch("orchestrator.graph.web_research_node", mock_web_research),
            patch("orchestrator.graph.rag_lookup_node", mock_rag_lookup),
            patch("orchestrator.graph.synthesize_node", mock_synthesize),
        ):
            from orchestrator.graph import build_graph

            graph = build_graph()
            result = await graph.ainvoke({"query": "simple factual question"})

        assert len(web_called) == 0
        assert len(rag_called) == 0
        assert result["final_answer"] == "direct answer"

    @pytest.mark.asyncio
    async def test_final_state_has_final_answer_set(self):
        async def mock_router(state):
            return {"route": "web_only"}

        async def mock_web_research(state):
            return {"web_result": "some findings", "retrieved_context": ["some findings"]}

        async def mock_rag_lookup(state):
            return {"rag_result": "", "retrieved_context": []}

        async def mock_synthesize(state):
            return {
                "final_answer": "This is the final answer.",
                "sources": ["https://example.com"],
            }

        with (
            patch("orchestrator.graph.router_node", mock_router),
            patch("orchestrator.graph.web_research_node", mock_web_research),
            patch("orchestrator.graph.rag_lookup_node", mock_rag_lookup),
            patch("orchestrator.graph.synthesize_node", mock_synthesize),
        ):
            from orchestrator.graph import build_graph

            graph = build_graph()
            result = await graph.ainvoke({"query": "test query"})

        assert "final_answer" in result
        assert result["final_answer"] == "This is the final answer."
        assert result["sources"] == ["https://example.com"]
