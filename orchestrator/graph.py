"""LangGraph StateGraph orchestrator definition."""
from langgraph.graph import END, StateGraph

from orchestrator.nodes.delegate import rag_lookup_node, web_research_node
from orchestrator.nodes.router import router_node
from orchestrator.nodes.synthesize import synthesize_node
from orchestrator.state import ResearchState


def _route_decision(state: ResearchState) -> str:
    """Map state["route"] to a graph edge target."""
    route = state.get("route", "both")
    if route in ("web_only", "rag_only", "direct", "both"):
        return route
    return "both"


def build_graph():
    """Build and compile the research orchestrator StateGraph."""
    graph = StateGraph(ResearchState)

    graph.add_node("router", router_node)
    graph.add_node("web_research", web_research_node)
    graph.add_node("rag_lookup", rag_lookup_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("router")

    # From router: fan out to correct path based on routing decision
    graph.add_conditional_edges(
        "router",
        _route_decision,
        {
            "web_only": "web_research",
            "rag_only": "rag_lookup",
            "both": "web_research",   # sequential: web -> rag -> synthesize
            "direct": "synthesize",
        },
    )

    # web_research: either go to rag (for "both") or directly to synthesize
    graph.add_conditional_edges(
        "web_research",
        lambda s: "rag_lookup" if s.get("route") == "both" else "synthesize",
        {
            "rag_lookup": "rag_lookup",
            "synthesize": "synthesize",
        },
    )

    graph.add_edge("rag_lookup", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()
