# mcp_tools/web_search/tests/test_server.py
import os
import json
import pytest
import respx
import httpx
from unittest.mock import patch
from fastmcp import Client
from fastmcp.exceptions import ToolError


TAVILY_SUCCESS_RESPONSE = {
    "results": [
        {
            "title": "Example Article",
            "url": "https://example.com/article",
            "content": "Some content about the topic.",
            "score": 0.95,
        },
        {
            "title": "Another Source",
            "url": "https://another.com",
            "content": "More content.",
            "score": 0.80,
        },
    ]
}


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


@pytest.mark.asyncio
async def test_successful_search_returns_correct_shape(mcp_server):
    """Successful Tavily response is returned as valid JSON with correct fields."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(200, json=TAVILY_SUCCESS_RESPONSE)
            )
            async with Client(mcp_server) as client:
                result = await client.call_tool("search_web", {"query": "AI research"})

    text = result.content[0].text
    data = json.loads(text)
    assert data["query"] == "AI research"
    assert len(data["results"]) == 2
    assert data["results"][0]["title"] == "Example Article"
    assert data["results"][0]["url"] == "https://example.com/article"
    assert isinstance(data["results"][0]["score"], float)
    assert "answer" not in data  # include_answer defaults to False


@pytest.mark.asyncio
async def test_include_answer_adds_answer_field(mcp_server):
    """When include_answer=True, the answer field is included in the response."""
    response_with_answer = {**TAVILY_SUCCESS_RESPONSE, "answer": "AI stands for artificial intelligence."}
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(200, json=response_with_answer)
            )
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "search_web", {"query": "what is AI", "include_answer": True}
                )

    data = json.loads(result.content[0].text)
    assert data["answer"] == "AI stands for artificial intelligence."


@pytest.mark.asyncio
async def test_include_answer_false_omits_answer(mcp_server):
    """Even if Tavily returns an answer, omit it when include_answer=False."""
    response_with_answer = {**TAVILY_SUCCESS_RESPONSE, "answer": "Some answer."}
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(200, json=response_with_answer)
            )
            async with Client(mcp_server) as client:
                result = await client.call_tool("search_web", {"query": "test"})

    data = json.loads(result.content[0].text)
    assert "answer" not in data
