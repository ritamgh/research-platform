"""Synthesize node — calls summariser agent to produce final answer."""
import json
import logging
import re

from langchain_anthropic import ChatAnthropic

from orchestrator.a2a_client import A2ACallError, call_agent
from orchestrator.config import OrchestratorConfig
from orchestrator.state import ResearchState

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https?://[^\s\)\]\>\"\']+")


def _extract_sources(text: str) -> list[str]:
    """Extract unique HTTP URLs from text."""
    return list(dict.fromkeys(_URL_PATTERN.findall(text)))


async def synthesize_node(state: ResearchState) -> dict:
    """Call the summariser agent and extract sources from the final answer.

    For 'direct' route: answer using LLM directly.
    For all other routes: delegate to summariser A2A agent.
    """
    query = state.get("query", "")
    route = state.get("route", "both")
    web_result = state.get("web_result", "")
    rag_result = state.get("rag_result", "")
    config = OrchestratorConfig.from_env()

    if route == "direct":
        llm = ChatAnthropic(model=config.router_model, temperature=0)
        try:
            response = llm.invoke(
                [{"role": "user", "content": f"Answer this research question concisely: {query}"}]
            )
            answer = response.content
        except Exception as exc:
            logger.error("Direct LLM call failed: %s", exc)
            answer = f"Unable to answer directly: {exc}"
        return {"final_answer": answer, "sources": _extract_sources(answer)}

    # Build summariser payload
    payload = json.dumps(
        {"query": query, "web_findings": web_result, "rag_findings": rag_result}
    )
    try:
        answer = await call_agent(config.summariser_url, payload, config.a2a_timeout)
    except A2ACallError as exc:
        logger.error("synthesize_node summariser call failed: %s", exc)
        # Fallback: combine available results directly
        parts = [p for p in [web_result, rag_result] if p]
        answer = "\n\n".join(parts) if parts else f"Research failed: {exc}"

    return {"final_answer": answer, "sources": _extract_sources(answer)}
