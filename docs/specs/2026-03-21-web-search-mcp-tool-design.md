# Web Search MCP Tool — Design Spec

**Date:** 2026-03-21
**Component:** `mcp_tools/web_search`
**Status:** Approved

---

## Overview

A FastMCP server wrapping the Tavily API, exposing a single `search_web` tool over Streamable HTTP transport. Used by the `web_research` agent (CrewAI) as its MCP tool server.

---

## Architecture

Single-file FastMCP server (`server.py`) with a uvicorn entrypoint (`main.py`). No layering or abstraction beyond what is needed for one tool.

### File Structure

```
mcp_tools/web_search/
├── server.py               # FastMCP instance, search_web tool, retry logic
├── main.py                 # uvicorn entrypoint
├── requirements.txt
└── tests/
    ├── test_server.py      # unit tests (httpx mocked via respx)
    └── test_integration.py # integration tests (skipped if no TAVILY_API_KEY)
```

Dockerfiles will be added in a separate containerization pass once all services are built.

---

## Transport

**Streamable HTTP** — FastMCP's current default. Single endpoint at `/mcp`. Agents connect as MCP clients via `httpx`.

---

## Tool Definition

```python
@mcp.tool()
async def search_web(
    query: str,
    num_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    include_answer: bool = False,
) -> str:
    ...
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | required | Search query string |
| `num_results` | `int` | 5 | Number of results (validated server-side: 1–10) |
| `search_depth` | `"basic"` \| `"advanced"` | `"basic"` | Tavily search depth |
| `include_answer` | `bool` | `False` | Whether to include Tavily's AI-generated answer |

`num_results` is validated server-side before the Tavily request. Values outside 1–10 raise `McpError` immediately (no Tavily call made).

### Return Shape

JSON string so agents can parse structure or treat as plain text:

```json
{
  "query": "...",
  "answer": "...",
  "results": [
    {"title": "...", "url": "...", "content": "...", "score": 0.95}
  ]
}
```

- `answer` is omitted when `include_answer=False`
- `score` is a float in the range 0.0–1.0, always present per Tavily's API contract
- Results with missing `title` or null `url` from Tavily are filtered out before returning
- Response size is implicitly bounded by `num_results` max of 10

---

## Data Flow

```
Agent (MCP client)
    │  POST /mcp  {"method": "tools/call", "params": {"name": "search_web", ...}}
    ▼
FastMCP (streamable HTTP)
    │  dispatches to search_web(query, num_results, search_depth, include_answer)
    ▼
retry wrapper (up to 3 attempts, exponential backoff: 1s → 2s → 4s)
    │  POST https://api.tavily.com/search
    ▼
Tavily API
    │  returns JSON results
    ▼
format as JSON string → FastMCP → HTTP response back to agent
```

---

## Error Handling

| Condition | Behavior |
|---|---|
| Transient HTTP (503, other 5xx) | Retry up to 3x; raise `McpError` after 3rd failure |
| Rate limit (429) | Retry up to 3x (counts toward same limit); raise `McpError` after 3rd failure |
| Connection error / timeout | Retry up to 3x; raise `McpError` after 3rd failure |
| Auth failure (401) | Raise `McpError` immediately — no retry |
| Bad request (400) | Raise `McpError` immediately — no retry |
| Invalid `num_results` | Raise `McpError` immediately before any Tavily call |
| Missing `TAVILY_API_KEY` | Server fails to start (process exits with error) — not deferred to first request |

**Retry timing:** Backoff is applied between attempts (not before the first). Attempt 1 is immediate; wait 1s before attempt 2; wait 2s before attempt 3; wait 4s before final failure.

**Retried conditions:** `httpx.TimeoutException`, `httpx.ConnectError`, and HTTP status codes 429, 500, 502, 503, 504.

`McpError` surfaces as a structured JSON-RPC error response to the calling agent.

---

## Testing

### Unit Tests (`test_server.py`)

Uses `respx` to mock `httpx` at the transport level. Tests:

- Successful search returns correctly shaped JSON
- `include_answer=False` omits the answer field from the response
- Transient 503 → retries → succeeds on 3rd attempt
- Transient 503 × 3 → raises `McpError`
- 429 (rate limit) triggers retry, exhausted → raises `McpError`
- `httpx.TimeoutException` triggers retry, exhausted → raises `McpError`
- 401 raises `McpError` immediately without retry
- `num_results=0` raises `McpError` immediately (no Tavily call)
- Missing `TAVILY_API_KEY` causes server startup failure (process exit)

### Integration Tests (`test_integration.py`)

- Skipped automatically if `TAVILY_API_KEY` is not set (`pytest.mark.skipif`)
- Marked with `@pytest.mark.integration` for CI exclusion
- One real Tavily search confirming result shape is valid

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TAVILY_API_KEY` | Yes | Tavily API key — checked at startup |

---

## Key Dependencies

```
fastmcp>=2.0
httpx>=0.27
python-dotenv>=1.0
respx>=0.21       # test dependency
pytest>=8.0       # test dependency
pytest-asyncio    # test dependency
```

---

## Port

Runs on port `9001` (as specified in docker-compose skeleton).
