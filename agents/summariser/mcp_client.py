"""MCP client for the citation_checker tool server (port 9004)."""
import os
from fastmcp import Client
from langsmith import traceable

CITATION_CHECKER_MCP_URL = os.environ.get("CITATION_CHECKER_MCP_URL", "http://localhost:9004/mcp")

# Module-level client — avoids creating a new HTTP/SSE connection on every call.
_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(CITATION_CHECKER_MCP_URL)
    return _client


@traceable(name="mcp_check_credibility", run_type="tool")
async def check_credibility(url: str) -> str:
    """Check the credibility score of a URL via the citation_checker MCP."""
    async with _get_client() as client:
        result = await client.call_tool("check_credibility", {"url": url})
        return result.content[0].text


@traceable(name="mcp_check_reachability", run_type="tool")
async def check_reachability(url: str) -> str:
    """Check whether a URL is reachable via the citation_checker MCP."""
    async with _get_client() as client:
        result = await client.call_tool("check_reachability", {"url": url})
        return result.content[0].text
