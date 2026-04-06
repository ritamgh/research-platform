"""Web research agent using CrewAI + web_search MCP tool."""
import os
from crewai import Agent, Crew, Task
from crewai.tools import tool as crewai_tool

from agents.web_research.mcp_client import search_web


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
        import asyncio
        return asyncio.run(_search(query))

    return _tool


def build_crew(search_fn=None) -> Crew:
    """Assemble the CrewAI crew for web research."""
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

    return Crew(agents=[researcher], tasks=[], verbose=False)


async def run_web_research(query: str, search_fn=None) -> str:
    """Run web research for the given query and return findings as a string."""
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

    task = Task(
        description=(
            f"Research the following question thoroughly:\n\n{query}\n\n"
            "Use the web_search tool to find relevant, recent information. "
            "Return a structured response with:\n"
            "1. A 2-3 sentence summary of the key findings\n"
            "2. Bullet points of the most important facts\n"
            "3. A list of sources (URLs) used"
        ),
        agent=researcher,
        expected_output=(
            "A structured research report with summary, key findings, and source URLs."
        ),
    )

    crew = Crew(agents=[researcher], tasks=[task], verbose=False)
    result = crew.kickoff()
    return str(result)
