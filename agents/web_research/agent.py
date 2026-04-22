"""Web research agent using CrewAI + web_search MCP tool."""
import asyncio
import concurrent.futures
import json
import os
import re

from crewai import Agent, Crew, Task
from crewai.tools import tool as crewai_tool
from langsmith import traceable

from agents.web_research.mcp_client import search_web

# Thread pool for running async MCP calls from sync CrewAI tool context.
# CrewAI tools are sync; uvicorn runs an async event loop — asyncio.run() would
# raise RuntimeError if called from within a running loop.
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_async_in_sync(coro):
    """Run an async coroutine safely from a sync context.

    If an event loop is already running (e.g. uvicorn), offloads to a thread
    with its own event loop. Otherwise falls back to asyncio.run().
    """
    try:
        asyncio.get_running_loop()
        future = _executor.submit(asyncio.run, coro)
        return future.result()
    except RuntimeError:
        return asyncio.run(coro)


def build_search_tool(search_fn=None):
    """Return a CrewAI-compatible tool that calls the web_search MCP server.

    ``search_fn`` is injectable for testing (defaults to the real MCP client).
    """
    _search = search_fn or search_web

    @crewai_tool("web_search")
    def _tool(query: str) -> str:
        """Search the web for recent information on a topic.

        Args:
            query: The search query string.

        Returns:
            JSON string of search results with titles, URLs, and snippets.
        """
        return _run_async_in_sync(_search(query))

    return _tool


# Module-level cache: search_fn -> Agent
# Avoids rebuilding the stateless Agent object on every request.
_agent_cache: dict[int, Agent] = {}


def _get_researcher(search_fn=None) -> tuple[Agent, object]:
    """Return a cached (Agent, search_tool) pair for the given search_fn."""
    cache_key = id(search_fn)
    if cache_key not in _agent_cache:
        search_tool = build_search_tool(search_fn)
        researcher = Agent(
            role="Web Research Specialist",
            goal=(
                "Search the web to find accurate, recent, and relevant information "
                "on the given research question. Cite your sources."
            ),
            backstory=(
                "You are an expert research analyst with deep experience finding "
                "authoritative sources on complex topics. You always provide "
                "structured findings with clear source citations."
            ),
            tools=[search_tool],
            verbose=False,
            allow_delegation=False,
            llm=os.environ.get("CREWAI_LLM", "openai/gpt-4o-mini"),
        )
        _agent_cache[cache_key] = (researcher, search_tool)
    return _agent_cache[cache_key]


def build_crew(search_fn=None) -> Crew:
    """Assemble the CrewAI crew for web research."""
    researcher, _ = _get_researcher(search_fn)
    return Crew(agents=[researcher], tasks=[], verbose=False)


@traceable(name="web_research", run_type="chain", tags=["agent"])
async def run_web_research(query: str, search_fn=None) -> str:
    """Run web research for the given query and return findings as a string.

    Fetches Tavily results once, passes them directly to the LLM as context
    (no tool call during the task), then guarantees URLs appear in the output.
    """
    _search = search_fn or search_web

    # Single Tavily call — reused for both LLM context and URL extraction.
    raw_json = await _search(query)
    raw_urls: list[str] = []
    formatted_results = raw_json
    try:
        raw_data = json.loads(raw_json)
        raw_urls = [r["url"] for r in raw_data.get("results", []) if r.get("url")]
        formatted_results = "\n\n".join(
            f"[{i + 1}] {r['title']}\nURL: {r['url']}\n{r.get('content', '')}"
            for i, r in enumerate(raw_data.get("results", []))
            if r.get("url")
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    researcher, _ = _get_researcher(search_fn)

    task = Task(
        description=(
            f"Summarise the following web search results for the question:\n\n{query}\n\n"
            f"SEARCH RESULTS (already fetched — do NOT call the web_search tool):\n\n"
            f"{formatted_results}\n\n"
            "Return:\n"
            "1. A 2-3 sentence summary of the key findings\n"
            "2. Bullet points of the most important facts"
        ),
        agent=researcher,
        expected_output=(
            "A concise research summary with key findings based on the provided results."
        ),
    )

    crew = Crew(agents=[researcher], tasks=[task], verbose=False)
    result = crew.kickoff()
    report = str(result)

    # Guarantee URLs appear in the output — append any the LLM omitted.
    if raw_urls:
        already_present = set(re.findall(r'https?://\S+', report))
        missing = [u for u in raw_urls if u not in already_present]
        if missing:
            report += "\n\nSources:\n" + "\n".join(f"- {u}" for u in missing)

    return report
