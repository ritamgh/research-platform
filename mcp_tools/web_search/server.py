# mcp_tools/web_search/server.py
import asyncio
import json
import os
from typing import Literal

import httpx
from fastmcp import FastMCP
from mcp.shared.exceptions import McpError, ErrorData
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, INVALID_REQUEST

mcp = FastMCP("web-search-tool")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Delays (seconds) before attempt 2 and attempt 3. Attempt 1 is immediate.
BACKOFF_DELAYS = [1, 2]


def _get_api_key() -> str:
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="TAVILY_API_KEY environment variable is not set"))
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
                    raise McpError(ErrorData(code=INVALID_REQUEST, message="Tavily authentication failed (401)"))
                if resp.status_code == 400:
                    raise McpError(ErrorData(code=INVALID_REQUEST, message=f"Bad Tavily request (400): {resp.text}"))
                if resp.status_code in RETRYABLE_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                    continue
                resp.raise_for_status()
                return resp.json()
            except McpError:
                raise
            except httpx.HTTPStatusError as e:
                raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Unexpected Tavily response: HTTP {e.response.status_code}"))
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = f"{type(e).__name__}: {e}"
                continue
    raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Tavily request failed after 3 attempts: {last_error}"))


@mcp.tool
async def search_web(
    query: str,
    num_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    include_answer: bool = False,
) -> str:
    """Search the web for recent information on a topic."""
    if not 1 <= num_results <= 10:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="num_results must be between 1 and 10 (inclusive)"))

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
