"""LangGraph state schema for the research orchestrator."""
import operator
from typing import Annotated, TypedDict


class ResearchState(TypedDict, total=False):
    # Input
    query: str

    # Routing decision: "web_only" | "rag_only" | "both" | "direct"
    route: str

    # Agent results
    web_result: str
    rag_result: str

    # Final output
    final_answer: str
    sources: list[str]

    # Eval metadata — operator.add reducer so both delegate nodes can append
    retrieved_context: Annotated[list[str], operator.add]

    # Error tracking
    error: str
