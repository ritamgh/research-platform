"""
Integration tests — require a live TAVILY_API_KEY.
Skipped automatically when the key is not set.
Run with: pytest tests/test_integration.py -m integration -v
"""
import json
import os

import pytest
from fastmcp import Client

pytestmark = pytest.mark.integration

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")


@pytest.fixture
def mcp_server():
    from mcp_tools.web_search.server import mcp
    return mcp


@pytest.mark.asyncio
@pytest.mark.skipif(not TAVILY_API_KEY, reason="TAVILY_API_KEY not set — skipping integration tests")
async def test_real_search_returns_valid_shape(mcp_server):
    """Live Tavily search returns a correctly shaped response."""
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "search_web",
            {"query": "large language model benchmarks 2025", "num_results": 3},
        )

    data = json.loads(result.content[0].text)
    assert data["query"] == "large language model benchmarks 2025"
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0
    first = data["results"][0]
    assert "title" in first
    assert "url" in first
    assert "content" in first
    assert isinstance(first["score"], float)
    assert 0.0 <= first["score"] <= 1.0
