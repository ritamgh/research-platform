"""Unit tests for orchestrator.state."""
import operator
from typing import get_type_hints


from orchestrator.state import ResearchState


class TestResearchState:
    def test_can_construct_with_all_fields(self):
        state: ResearchState = {
            "query": "What is LangGraph?",
            "route": "web_only",
            "web_result": "LangGraph is a library for building stateful agents.",
            "rag_result": "Found 3 relevant documents.",
            "final_answer": "LangGraph is a framework for building stateful, multi-actor applications.",
            "sources": ["https://example.com/langgraph"],
            "retrieved_context": ["context chunk 1", "context chunk 2"],
            "error": "",
        }
        assert state["query"] == "What is LangGraph?"
        assert state["route"] == "web_only"
        assert state["web_result"] == "LangGraph is a library for building stateful agents."
        assert state["rag_result"] == "Found 3 relevant documents."
        assert state["final_answer"] == "LangGraph is a framework for building stateful, multi-actor applications."
        assert state["sources"] == ["https://example.com/langgraph"]
        assert state["retrieved_context"] == ["context chunk 1", "context chunk 2"]
        assert state["error"] == ""

    def test_retrieved_context_uses_operator_add_reducer(self):
        hints = get_type_hints(ResearchState, include_extras=True)
        annotation = hints["retrieved_context"]
        # Should be Annotated[list[str], operator.add]
        assert hasattr(annotation, "__metadata__"), (
            "retrieved_context should be Annotated with metadata"
        )
        metadata = annotation.__metadata__
        assert len(metadata) == 1, "Annotated should have exactly one metadata entry"
        assert metadata[0] is operator.add, (
            "retrieved_context reducer should be operator.add"
        )

    def test_retrieved_context_reducer_merges_lists(self):
        # Verify operator.add actually concatenates lists (not just adds numbers)
        left = ["chunk a", "chunk b"]
        right = ["chunk c"]
        merged = operator.add(left, right)
        assert merged == ["chunk a", "chunk b", "chunk c"]

    def test_can_construct_with_only_query(self):
        state: ResearchState = {"query": "minimal state"}
        assert state["query"] == "minimal state"
        assert "route" not in state
        assert "web_result" not in state

    def test_used_as_langgraph_state_without_error(self):
        from langgraph.graph import StateGraph

        graph = StateGraph(ResearchState)
        graph.add_node("noop", lambda s: {})
        graph.set_entry_point("noop")
        compiled = graph.compile()
        assert compiled is not None
