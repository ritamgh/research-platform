"""Delegate nodes — call A2A agents to gather research results."""
import logging

from orchestrator.a2a_client import A2ACallError, call_agent
from orchestrator.config import OrchestratorConfig
from orchestrator.state import ResearchState

logger = logging.getLogger(__name__)


async def web_research_node(state: ResearchState) -> dict:
    """Call the web_research A2A agent with the query.

    Returns updates to state: web_result and retrieved_context.
    On failure, sets error without crashing.
    """
    query = state.get("query", "")
    config = OrchestratorConfig.from_env()
    try:
        result = await call_agent(config.web_research_url, query, config.a2a_timeout)
        return {"web_result": result, "retrieved_context": [result]}
    except A2ACallError as exc:
        logger.error("web_research_node failed: %s", exc)
        return {"web_result": "", "error": str(exc)}


async def rag_lookup_node(state: ResearchState) -> dict:
    """Call the rag A2A agent with the query.

    Returns updates to state: rag_result and retrieved_context.
    On failure, sets error without crashing.
    """
    query = state.get("query", "")
    config = OrchestratorConfig.from_env()
    try:
        result = await call_agent(config.rag_url, query, config.a2a_timeout)
        return {"rag_result": result, "retrieved_context": [result]}
    except A2ACallError as exc:
        logger.error("rag_lookup_node failed: %s", exc)
        return {"rag_result": "", "error": str(exc)}
