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


@pytest.mark.asyncio
async def test_transient_503_retries_and_succeeds(mcp_server):
    """503 on first two attempts, success on third attempt."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        with patch("mcp_tools.web_search.server.asyncio.sleep"):
            async with respx.mock:
                route = respx.post("https://api.tavily.com/search")
                route.side_effect = [
                    httpx.Response(503),
                    httpx.Response(503),
                    httpx.Response(200, json=TAVILY_SUCCESS_RESPONSE),
                ]
                async with Client(mcp_server) as client:
                    result = await client.call_tool("search_web", {"query": "test"})

    data = json.loads(result.content[0].text)
    assert len(data["results"]) == 2
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_three_consecutive_503s_raises_error(mcp_server):
    """Three consecutive 503s exhaust retries and raise ToolError."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        with patch("mcp_tools.web_search.server.asyncio.sleep"):
            async with respx.mock:
                respx.post("https://api.tavily.com/search").mock(
                    return_value=httpx.Response(503)
                )
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("search_web", {"query": "test"})


@pytest.mark.asyncio
async def test_429_rate_limit_retries_then_raises(mcp_server):
    """429 rate limit responses are retried; raises ToolError after exhaustion."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        with patch("mcp_tools.web_search.server.asyncio.sleep"):
            async with respx.mock:
                respx.post("https://api.tavily.com/search").mock(
                    return_value=httpx.Response(429)
                )
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("search_web", {"query": "test"})


@pytest.mark.asyncio
async def test_timeout_retries_then_raises(mcp_server):
    """httpx.TimeoutException is retried; raises ToolError after exhaustion."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        with patch("mcp_tools.web_search.server.asyncio.sleep"):
            async with respx.mock:
                respx.post("https://api.tavily.com/search").mock(
                    side_effect=httpx.TimeoutException("timed out")
                )
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("search_web", {"query": "test"})


@pytest.mark.asyncio
async def test_401_raises_immediately_without_retry(mcp_server):
    """401 auth failure raises ToolError immediately — no retry."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "bad-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(401)
            )
            async with Client(mcp_server) as client:
                with pytest.raises(ToolError):
                    await client.call_tool("search_web", {"query": "test"})

    # Must only call Tavily once — no retries on 401
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_400_bad_request_raises_immediately_without_retry(mcp_server):
    """400 bad request raises ToolError immediately — no retry."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(400, text="bad request")
            )
            async with Client(mcp_server) as client:
                with pytest.raises(ToolError):
                    await client.call_tool("search_web", {"query": "test"})

    assert route.call_count == 1  # no retry on 400


@pytest.mark.asyncio
async def test_num_results_zero_raises_without_tavily_call(mcp_server):
    """num_results=0 raises ToolError before any Tavily request is made."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search")
            async with Client(mcp_server) as client:
                with pytest.raises(ToolError):
                    await client.call_tool("search_web", {"query": "test", "num_results": 0})

    assert route.call_count == 0  # Tavily was never called


@pytest.mark.asyncio
async def test_num_results_eleven_raises_without_tavily_call(mcp_server):
    """num_results=11 raises ToolError before any Tavily request."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search")
            async with Client(mcp_server) as client:
                with pytest.raises(ToolError):
                    await client.call_tool("search_web", {"query": "test", "num_results": 11})

    assert route.call_count == 0


@pytest.mark.asyncio
async def test_num_results_one_is_valid(mcp_server):
    """num_results=1 (lower boundary) is accepted."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(200, json=TAVILY_SUCCESS_RESPONSE)
            )
            async with Client(mcp_server) as client:
                result = await client.call_tool("search_web", {"query": "test", "num_results": 1})

    data = json.loads(result.content[0].text)
    assert "results" in data


@pytest.mark.asyncio
async def test_num_results_ten_is_valid(mcp_server):
    """num_results=10 (upper boundary) is accepted."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(200, json=TAVILY_SUCCESS_RESPONSE)
            )
            async with Client(mcp_server) as client:
                result = await client.call_tool("search_web", {"query": "test", "num_results": 10})

    data = json.loads(result.content[0].text)
    assert "results" in data


@pytest.mark.asyncio
async def test_empty_query_raises_without_tavily_call(mcp_server):
    """Empty or blank query raises ToolError before any Tavily request."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search")
            async with Client(mcp_server) as client:
                with pytest.raises(ToolError):
                    await client.call_tool("search_web", {"query": ""})

    assert route.call_count == 0  # Tavily was never called


@pytest.mark.asyncio
async def test_results_with_null_url_are_filtered(mcp_server):
    """Results where url is null are excluded from the response."""
    response = {
        "results": [
            {"title": "Good Result", "url": "https://example.com", "content": "...", "score": 0.9},
            {"title": "No URL Result", "url": None, "content": "...", "score": 0.8},
        ]
    }
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(200, json=response)
            )
            async with Client(mcp_server) as client:
                result = await client.call_tool("search_web", {"query": "test"})

    data = json.loads(result.content[0].text)
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_results_with_missing_title_are_filtered(mcp_server):
    """Results missing a title field are excluded from the response."""
    response = {
        "results": [
            {"title": "Good Result", "url": "https://example.com", "content": "...", "score": 0.9},
            {"url": "https://notitle.com", "content": "...", "score": 0.7},  # no title key
        ]
    }
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(200, json=response)
            )
            async with Client(mcp_server) as client:
                result = await client.call_tool("search_web", {"query": "test"})

    data = json.loads(result.content[0].text)
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "https://example.com"
