"""Router node — LLM classifies query into routing decision."""
import json
import logging

from langchain_anthropic import ChatAnthropic

from orchestrator.config import OrchestratorConfig
from orchestrator.state import ResearchState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a research query router. Classify the query into exactly one category:

- "web_only": Needs current/recent information (news, latest papers, current events, live data)
- "rag_only": Answerable from a local document corpus (specific docs, stored knowledge)
- "both": Benefits from both web search and local corpus
- "direct": Simple factual question answerable without external sources

Respond with ONLY valid JSON: {"route": "<category>", "reasoning": "<one sentence>"}
No markdown, no extra text."""

_VALID_ROUTES = frozenset({"web_only", "rag_only", "both", "direct"})


async def router_node(state: ResearchState) -> dict:
    """Classify the query and return routing decision.

    Returns a dict updating state["route"].
    Falls back to "both" on any LLM or parse failure.
    """
    query = state.get("query", "")
    if not query:
        return {"route": "both"}

    config = OrchestratorConfig.from_env()
    llm = ChatAnthropic(model=config.router_model, temperature=0)

    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Query: {query}"},
            ]
        )
        raw = response.content
        parsed = json.loads(raw)
        route = parsed.get("route", "both")
        if route not in _VALID_ROUTES:
            logger.warning("Router returned unknown route %r, defaulting to 'both'", route)
            route = "both"
        return {"route": route}
    except Exception as exc:
        logger.warning("Router failed (%s), defaulting to 'both'", exc)
        return {"route": "both"}
