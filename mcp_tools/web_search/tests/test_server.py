# mcp_tools/web_search/tests/test_server.py
import os
import pytest
from unittest.mock import patch
from fastmcp import Client
from fastmcp.exceptions import ToolError


@pytest.fixture
def mcp_server():
    from mcp_tools.web_search.server import mcp
    return mcp


@pytest.mark.asyncio
async def test_missing_api_key_raises_mcp_error(mcp_server):
    """search_web raises ToolError when TAVILY_API_KEY is not set."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
        async with Client(mcp_server) as client:
            with pytest.raises(ToolError):
                await client.call_tool("search_web", {"query": "test"})
