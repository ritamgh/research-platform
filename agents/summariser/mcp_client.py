"""MCP client for the citation_checker tool server (port 9004)."""
import os
from fastmcp import Client

CITATION_CHECKER_MCP_URL = os.environ.get("CITATION_CHECKER_MCP_URL", "http://localhost:9004/mcp")


async def check_credibility(url: str) -> str:
    """Check the credibility score of a URL via the citation_checker MCP."""
    async with Client(CITATION_CHECKER_MCP_URL) as client:
        result = await client.call_tool("check_credibility", {"url": url})
        return result.content[0].text


async def check_reachability(url: str) -> str:
    """Check whether a URL is reachable via the citation_checker MCP."""
    async with Client(CITATION_CHECKER_MCP_URL) as client:
        result = await client.call_tool("check_reachability", {"url": url})
        return result.content[0].text
