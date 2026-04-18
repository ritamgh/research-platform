"""MCP client for the web_search tool server (port 9001)."""
import os
from fastmcp import Client

WEB_SEARCH_MCP_URL = os.environ.get("WEB_SEARCH_MCP_URL", "http://localhost:9001/mcp")

# Module-level client — avoids creating a new HTTP/SSE connection on every call.
_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(WEB_SEARCH_MCP_URL)
    return _client


async def search_web(query: str, num_results: int = 5) -> str:
    """Call the web_search MCP tool and return results as a string."""
    async with _get_client() as client:
        result = await client.call_tool(
            "search_web",
            {"query": query, "num_results": num_results},
        )
        return result.content[0].text
