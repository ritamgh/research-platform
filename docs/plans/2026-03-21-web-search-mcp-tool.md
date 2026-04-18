# Web Search MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastMCP server that exposes a `search_web` tool over Streamable HTTP, wrapping the Tavily search API with retry logic and structured JSON responses.

**Architecture:** Single `server.py` owns the FastMCP instance, tool definition, Tavily HTTP client, and retry logic. `main.py` is the uvicorn entrypoint that validates the API key before starting. Tests use FastMCP's in-process `Client(mcp)` with `respx` to mock httpx at the transport level.

**Tech Stack:** `fastmcp>=2.0`, `httpx>=0.27`, `respx>=0.21` (test), `pytest-asyncio`, `python-dotenv`

**Spec:** `docs/superpowers/specs/2026-03-21-web-search-mcp-tool-design.md`

---

## File Map

| File | Role |
|---|---|
| `mcp_tools/web_search/server.py` | FastMCP instance, `search_web` tool, `_call_tavily()` with retry, `_get_api_key()` validator |
| `mcp_tools/web_search/main.py` | Startup API key check + `mcp.run()` entrypoint |
| `mcp_tools/web_search/requirements.txt` | Runtime + test dependencies |
| `mcp_tools/web_search/tests/__init__.py` | Empty — makes tests a package |
| `mcp_tools/web_search/tests/test_server.py` | Unit tests (httpx mocked via respx) |
| `mcp_tools/web_search/tests/test_integration.py` | Integration tests (skipped if no `TAVILY_API_KEY`) |

---

## Task 1: Project scaffold

**Files:**
- Create: `mcp_tools/web_search/requirements.txt`
- Create: `mcp_tools/web_search/pytest.ini`
- Create: `mcp_tools/web_search/tests/__init__.py`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p mcp_tools/web_search/tests
touch mcp_tools/web_search/tests/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
# mcp_tools/web_search/requirements.txt
fastmcp>=2.0
httpx>=0.27
python-dotenv>=1.0

# test dependencies
pytest>=8.0
pytest-asyncio>=0.24
respx>=0.21
```

- [ ] **Step 3: Write pytest.ini**

```ini
# mcp_tools/web_search/pytest.ini
[pytest]
asyncio_mode = auto
markers =
    integration: marks tests as integration tests (require live TAVILY_API_KEY)
```

This must exist before running any tests — it configures asyncio mode so `@pytest.mark.asyncio` works without explicit `asyncio_mode` arguments.

- [ ] **Step 4: Commit**

```bash
git add mcp_tools/web_search/
git commit -m "chore: scaffold web_search MCP tool directory"
```

---

## Task 2: Server skeleton and API key validation

**Files:**
- Create: `mcp_tools/web_search/server.py`
- Create: `mcp_tools/web_search/tests/test_server.py` (first test only)

- [ ] **Step 1: Write the failing test for missing API key**

```python
# mcp_tools/web_search/tests/test_server.py
import os
import pytest
import pytest_asyncio
from unittest.mock import patch
from fastmcp import Client
from mcp.shared.exceptions import McpError


@pytest.mark.asyncio
async def test_missing_api_key_raises_on_tool_call():
    """search_web raises McpError when TAVILY_API_KEY is not set."""
    with patch.dict(os.environ, {}, clear=True):
        # Remove the key if present
        os.environ.pop("TAVILY_API_KEY", None)
        from importlib import reload
        import mcp_tools.web_search.server as srv_module  # noqa: F401
        # Import the mcp instance
        from mcp_tools.web_search.server import mcp
        async with Client(mcp) as client:
            with pytest.raises(McpError):
                await client.call_tool("search_web", {"query": "test"})
```

> **Note on test isolation:** Because `_get_api_key()` reads `os.environ` at call time (not import time), patching `os.environ` before calling the tool is sufficient. No module reload needed.

Revised test (simpler):

```python
# mcp_tools/web_search/tests/test_server.py
import os
import pytest
from unittest.mock import patch
from fastmcp import Client
from mcp.shared.exceptions import McpError


@pytest.fixture
def mcp_server():
    from mcp_tools.web_search.server import mcp
    return mcp


@pytest.mark.asyncio
async def test_missing_api_key_raises_mcp_error(mcp_server):
    """search_web raises McpError when TAVILY_API_KEY is not set."""
    with patch.dict(os.environ, {}, clear=True):
        async with Client(mcp_server) as client:
            with pytest.raises(McpError):
                await client.call_tool("search_web", {"query": "test"})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd mcp_tools/web_search
pip install -e ".[test]" 2>/dev/null || pip install -r requirements.txt
pytest tests/test_server.py::test_missing_api_key_raises_mcp_error -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `server.py` does not exist yet.

- [ ] **Step 3: Write the minimal server.py**

```python
# mcp_tools/web_search/server.py
import asyncio
import json
import os
from typing import Literal

import httpx
from fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorCode

mcp = FastMCP("web-search-tool")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Delays (seconds) before attempt 2 and attempt 3. Attempt 1 is immediate.
BACKOFF_DELAYS = [1, 2]


def _get_api_key() -> str:
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        raise McpError(ErrorCode.InternalError, "TAVILY_API_KEY environment variable is not set")
    return key


async def _call_tavily(payload: dict) -> dict:
    api_key = _get_api_key()
    last_error = "unknown error"
    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            if attempt > 0:
                await asyncio.sleep(BACKOFF_DELAYS[attempt - 1])
            try:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, **payload},
                    timeout=30.0,
                )
                if resp.status_code == 401:
                    raise McpError(ErrorCode.InvalidRequest, "Tavily authentication failed (401)")
                if resp.status_code == 400:
                    raise McpError(ErrorCode.InvalidRequest, f"Bad Tavily request (400): {resp.text}")
                if resp.status_code in RETRYABLE_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                    continue
                resp.raise_for_status()
                return resp.json()
            except McpError:
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = str(e)
                continue
    raise McpError(ErrorCode.InternalError, f"Tavily request failed after 3 attempts: {last_error}")


@mcp.tool
async def search_web(
    query: str,
    num_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    include_answer: bool = False,
) -> str:
    """Search the web for recent information on a topic."""
    if not 1 <= num_results <= 10:
        raise McpError(ErrorCode.InvalidParams, "num_results must be between 1 and 10 (inclusive)")

    payload = {
        "query": query,
        "max_results": num_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
    }
    data = await _call_tavily(payload)

    # Filter results missing required fields
    raw_results = data.get("results", [])
    filtered = [r for r in raw_results if r.get("url") is not None and r.get("title") is not None]

    output: dict = {
        "query": query,
        "results": [
            {
                "title": r["title"],
                "url": r["url"],
                "content": r.get("content", ""),
                "score": float(r.get("score", 0.0)),
            }
            for r in filtered
        ],
    }
    if include_answer and data.get("answer"):
        output["answer"] = data["answer"]

    return json.dumps(output)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_server.py::test_missing_api_key_raises_mcp_error -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/web_search/server.py mcp_tools/web_search/tests/test_server.py
git commit -m "feat: add web_search MCP server skeleton with API key validation"
```

---

## Task 3: Happy path — successful search

**Files:**
- Modify: `mcp_tools/web_search/tests/test_server.py`

- [ ] **Step 1: Add the happy path test**

Add to `test_server.py` after the existing test:

```python
import respx
import json


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

    text = result[0].text
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

    data = json.loads(result[0].text)
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

    data = json.loads(result[0].text)
    assert "answer" not in data
```

Also add `import httpx` at the top of `test_server.py`.

- [ ] **Step 2: Run the new tests**

```bash
pytest tests/test_server.py -k "successful_search or include_answer" -v
```

Expected: All 3 `PASSED` (server.py is already implemented)

- [ ] **Step 3: Commit**

```bash
git add mcp_tools/web_search/tests/test_server.py
git commit -m "test: add happy path tests for search_web tool"
```

---

## Task 4: Retry behavior

**Files:**
- Modify: `mcp_tools/web_search/tests/test_server.py`

- [ ] **Step 1: Add retry tests**

```python
@pytest.mark.asyncio
async def test_transient_503_retries_and_succeeds(mcp_server):
    """503 on first two attempts, success on third attempt."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        # Patch asyncio.sleep to avoid real delays in tests
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

    data = json.loads(result[0].text)
    assert len(data["results"]) == 2
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_three_consecutive_503s_raises_mcp_error(mcp_server):
    """Three consecutive 503s exhaust retries and raise McpError."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        with patch("mcp_tools.web_search.server.asyncio.sleep"):
            async with respx.mock:
                respx.post("https://api.tavily.com/search").mock(
                    return_value=httpx.Response(503)
                )
                async with Client(mcp_server) as client:
                    with pytest.raises(McpError):
                        await client.call_tool("search_web", {"query": "test"})


@pytest.mark.asyncio
async def test_429_rate_limit_retries_then_raises(mcp_server):
    """429 rate limit responses are retried; raises McpError after exhaustion."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        with patch("mcp_tools.web_search.server.asyncio.sleep"):
            async with respx.mock:
                respx.post("https://api.tavily.com/search").mock(
                    return_value=httpx.Response(429)
                )
                async with Client(mcp_server) as client:
                    with pytest.raises(McpError):
                        await client.call_tool("search_web", {"query": "test"})


@pytest.mark.asyncio
async def test_timeout_retries_then_raises(mcp_server):
    """httpx.TimeoutException is retried; raises McpError after exhaustion."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        with patch("mcp_tools.web_search.server.asyncio.sleep"):
            async with respx.mock:
                respx.post("https://api.tavily.com/search").mock(
                    side_effect=httpx.TimeoutException("timed out")
                )
                async with Client(mcp_server) as client:
                    with pytest.raises(McpError):
                        await client.call_tool("search_web", {"query": "test"})
```

- [ ] **Step 2: Run the retry tests**

```bash
pytest tests/test_server.py -k "retry or 503 or 429 or timeout" -v
```

Expected: All 4 `PASSED`

- [ ] **Step 3: Commit**

```bash
git add mcp_tools/web_search/tests/test_server.py
git commit -m "test: add retry behavior tests for transient errors"
```

---

## Task 5: Immediate failure cases

**Files:**
- Modify: `mcp_tools/web_search/tests/test_server.py`

- [ ] **Step 1: Add immediate failure tests**

```python
@pytest.mark.asyncio
async def test_401_raises_immediately_without_retry(mcp_server):
    """401 auth failure raises McpError immediately — no retry."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "bad-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(401)
            )
            async with Client(mcp_server) as client:
                with pytest.raises(McpError):
                    await client.call_tool("search_web", {"query": "test"})

        # Must only call Tavily once — no retries on 401
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_num_results_zero_raises_mcp_error_without_tavily_call(mcp_server):
    """num_results=0 raises McpError before any Tavily request is made."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search")
            async with Client(mcp_server) as client:
                with pytest.raises(McpError):
                    await client.call_tool("search_web", {"query": "test", "num_results": 0})

        assert route.call_count == 0  # Tavily was never called


@pytest.mark.asyncio
async def test_num_results_eleven_raises_mcp_error(mcp_server):
    """num_results=11 (above max) raises McpError before any Tavily request."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search")
            async with Client(mcp_server) as client:
                with pytest.raises(McpError):
                    await client.call_tool("search_web", {"query": "test", "num_results": 11})

        assert route.call_count == 0
```

- [ ] **Step 2: Add boundary and 400 tests**

```python
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

    data = json.loads(result[0].text)
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

    data = json.loads(result[0].text)
    assert "results" in data


@pytest.mark.asyncio
async def test_400_bad_request_raises_immediately_without_retry(mcp_server):
    """400 bad request raises McpError immediately — no retry."""
    with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
        async with respx.mock:
            route = respx.post("https://api.tavily.com/search").mock(
                return_value=httpx.Response(400, text="bad request")
            )
            async with Client(mcp_server) as client:
                with pytest.raises(McpError):
                    await client.call_tool("search_web", {"query": "test"})

        assert route.call_count == 1  # no retry on 400
```

- [ ] **Step 3: Run the immediate failure tests**

```bash
pytest tests/test_server.py -k "401 or num_results or 400 or boundary" -v
```

Expected: All 6 `PASSED`

- [ ] **Step 4: Commit**

```bash
git add mcp_tools/web_search/tests/test_server.py
git commit -m "test: add immediate failure cases (401, 400, invalid/boundary num_results)"
```

---

## Task 6: Response filtering

**Files:**
- Modify: `mcp_tools/web_search/tests/test_server.py`

- [ ] **Step 1: Add response filtering tests**

```python
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

    data = json.loads(result[0].text)
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

    data = json.loads(result[0].text)
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "https://example.com"
```

- [ ] **Step 2: Run the filtering tests**

```bash
pytest tests/test_server.py -k "filtered or filter" -v
```

Expected: Both `PASSED`

- [ ] **Step 3: Run the full unit test suite**

```bash
pytest tests/test_server.py -v
```

Expected: All tests `PASSED`

- [ ] **Step 4: Commit**

```bash
git add mcp_tools/web_search/tests/test_server.py
git commit -m "test: add response filtering tests for malformed Tavily results"
```

---

## Task 7: Entrypoint and integration tests

**Files:**
- Create: `mcp_tools/web_search/main.py`
- Create: `mcp_tools/web_search/tests/test_integration.py`

- [ ] **Step 1: Write main.py**

```python
# mcp_tools/web_search/main.py
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("TAVILY_API_KEY"):
    print("ERROR: TAVILY_API_KEY environment variable is not set", file=sys.stderr)
    sys.exit(1)

from mcp_tools.web_search.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9001)
```

- [ ] **Step 2: Write the integration test**

```python
# mcp_tools/web_search/tests/test_integration.py
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

    data = json.loads(result[0].text)
    assert data["query"] == "large language model benchmarks 2025"
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0
    first = data["results"][0]
    assert "title" in first
    assert "url" in first
    assert "content" in first
    assert isinstance(first["score"], float)
    assert 0.0 <= first["score"] <= 1.0
```

- [ ] **Step 3: Run the integration test (requires real API key)**

```bash
# Only run if you have a real TAVILY_API_KEY set
pytest tests/test_integration.py -m integration -v
```

Expected: `PASSED` if key is valid; `SKIPPED` if key is not set.

- [ ] **Step 4: Confirm unit tests still pass**

```bash
pytest tests/test_server.py -v
```

Expected: All `PASSED`

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/web_search/main.py mcp_tools/web_search/tests/test_integration.py
git commit -m "feat: add main.py entrypoint and integration tests for web_search MCP tool"
```

---

## Verification Checklist

Before calling this complete:

- [ ] `pytest tests/test_server.py -v` — all pass with no warnings
- [ ] `pytest tests/test_integration.py -m integration -v` — passes with real key, skips without
- [ ] `python main.py` without `TAVILY_API_KEY` set prints error and exits 1
- [ ] `python main.py` with key set starts the server on port 9001
- [ ] `GET http://localhost:9001/mcp` returns a valid MCP response (or 405 — server is alive)
