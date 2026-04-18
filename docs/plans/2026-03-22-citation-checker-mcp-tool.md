# Citation Checker MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastMCP tool server with two tools — `check_credibility` (offline domain/TLD heuristics) and `check_reachability` (HTTP HEAD check) — on port 9004.

**Architecture:** Mirrors the existing `web_search`, `vector_db`, and `file_reader` patterns exactly. `server.py` contains all tool logic; `main.py` is the entrypoint. No required env vars. All unit tests are mocked (respx for HTTP, no filesystem fixtures needed).

**Tech Stack:** FastMCP 2.x, httpx, respx, python-dotenv, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-22-citation-checker-mcp-tool-design.md`

---

## Files

| File | Action | Purpose |
|---|---|---|
| `mcp_tools/citation_checker/__init__.py` | Create | Package marker |
| `mcp_tools/citation_checker/server.py` | Create | FastMCP instance, domain sets, `_score_url`, `check_credibility`, `check_reachability` |
| `mcp_tools/citation_checker/main.py` | Create | Entrypoint: `load_dotenv` + `mcp.run(port=9004)` |
| `mcp_tools/citation_checker/requirements.txt` | Create | Python dependencies |
| `mcp_tools/citation_checker/pytest.ini` | Create | `asyncio_mode = auto` |
| `mcp_tools/citation_checker/tests/__init__.py` | Create | Package marker |
| `mcp_tools/citation_checker/tests/test_server.py` | Create | 25 unit tests (credibility + reachability, all mocked) |
| `mcp_tools/citation_checker/tests/test_integration.py` | Create | 1 live reachability test |

---

## Task 1: Scaffold the module

**Files:**
- Create: `mcp_tools/citation_checker/__init__.py`
- Create: `mcp_tools/citation_checker/tests/__init__.py`
- Create: `mcp_tools/citation_checker/requirements.txt`
- Create: `mcp_tools/citation_checker/pytest.ini`
- Create: `mcp_tools/citation_checker/main.py`

This task is mechanical (no logic). Verify the files yourself — no code review needed.

- [ ] **Step 1: Create package markers**

```bash
mkdir -p mcp_tools/citation_checker/tests
touch mcp_tools/citation_checker/__init__.py
touch mcp_tools/citation_checker/tests/__init__.py
```

- [ ] **Step 2: Create `mcp_tools/citation_checker/requirements.txt`**

```
fastmcp>=2.0
httpx>=0.27
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.24
respx>=0.21
```

- [ ] **Step 3: Create `mcp_tools/citation_checker/pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
markers =
    integration: marks tests as integration tests
```

- [ ] **Step 4: Create `mcp_tools/citation_checker/main.py`**

```python
# mcp_tools/citation_checker/main.py
from dotenv import load_dotenv

load_dotenv()

from mcp_tools.citation_checker.server import mcp  # noqa: E402

if __name__ == "__main__":
    # Binds to 0.0.0.0 — deploy behind an authenticated proxy or in a network-isolated container.
    mcp.run(transport="http", host="0.0.0.0", port=9004)
```

- [ ] **Step 5: Commit scaffold**

```bash
git add mcp_tools/citation_checker/__init__.py \
        mcp_tools/citation_checker/tests/__init__.py \
        mcp_tools/citation_checker/requirements.txt \
        mcp_tools/citation_checker/pytest.ini \
        mcp_tools/citation_checker/main.py
git commit -m "chore: scaffold mcp_tools/citation_checker module"
```

---

## Task 2: `check_credibility` — TDD

**Files:**
- Create: `mcp_tools/citation_checker/server.py`
- Create: `mcp_tools/citation_checker/tests/test_server.py`

Write all 16 credibility tests first (they will fail), then implement `server.py` to pass them.

### Step 1: Write the failing tests

- [ ] **Create `mcp_tools/citation_checker/tests/test_server.py` with all credibility tests**

```python
# mcp_tools/citation_checker/tests/test_server.py
import json
import pytest
import respx
import httpx
from fastmcp import Client
from fastmcp.exceptions import ToolError


@pytest.fixture
def mcp_server():
    from mcp_tools.citation_checker.server import mcp
    return mcp


# ---------------------------------------------------------------------------
# check_credibility — input validation
# ---------------------------------------------------------------------------

async def test_credibility_empty_url_raises(mcp_server):
    """Empty url raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_credibility", {"url": ""})


async def test_credibility_schemeless_url_raises(mcp_server):
    """Schemeless string (no ://) produces empty hostname and raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_credibility", {"url": "arxiv.org/abs/123"})


async def test_credibility_unparseable_url_raises(mcp_server):
    """String with no parseable hostname raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_credibility", {"url": "not-a-url"})


# ---------------------------------------------------------------------------
# check_credibility — scheme handling
# ---------------------------------------------------------------------------

async def test_credibility_ftp_scheme_accepted(mcp_server):
    """Non-http/https scheme is accepted; scoring is domain-based only."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "ftp://arxiv.org/paper"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["label"] == "high"


# ---------------------------------------------------------------------------
# check_credibility — tier 1: research domains
# ---------------------------------------------------------------------------

async def test_credibility_research_domain(mcp_server):
    """Known research domain (arxiv.org) scores 0.9 / high / 'Known research publisher'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://arxiv.org/abs/2301.00001"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["label"] == "high"
    assert data["reason"] == "Known research publisher"


# ---------------------------------------------------------------------------
# check_credibility — tier 2: credible news/health domains
# ---------------------------------------------------------------------------

async def test_credibility_news_domain(mcp_server):
    """Known news domain (reuters.com) scores 0.9 / high / 'Known credible news/health source'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://reuters.com/article/x"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["label"] == "high"
    assert data["reason"] == "Known credible news/health source"


# ---------------------------------------------------------------------------
# check_credibility — tier 3: blog hosts
# ---------------------------------------------------------------------------

async def test_credibility_blog_host(mcp_server):
    """Free blog host (wordpress.com) scores 0.2 / low / 'Free blog host'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://wordpress.com/post/123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.2
    assert data["label"] == "low"
    assert data["reason"] == "Free blog host"


# ---------------------------------------------------------------------------
# check_credibility — tier 4: URL shorteners
# ---------------------------------------------------------------------------

async def test_credibility_url_shortener(mcp_server):
    """URL shortener (bit.ly) scores 0.2 / low / 'URL shortener'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://bit.ly/abc123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.2
    assert data["label"] == "low"
    assert data["reason"] == "URL shortener"


# ---------------------------------------------------------------------------
# check_credibility — tier 5: low-credibility TLDs
# ---------------------------------------------------------------------------

async def test_credibility_low_tld(mcp_server):
    """Low-credibility TLD (.xyz) scores 0.1 / low."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://example.xyz/page"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.1
    assert data["label"] == "low"


# ---------------------------------------------------------------------------
# check_credibility — tier 6: TLD fallback
# ---------------------------------------------------------------------------

async def test_credibility_edu_tld(mcp_server):
    """.edu TLD fallback scores 0.85 / high."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://mit.edu/research/paper"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.85
    assert data["label"] == "high"


async def test_credibility_gov_tld(mcp_server):
    """.gov TLD fallback scores 0.85 / high."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://nasa.gov/report"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.85
    assert data["label"] == "high"


async def test_credibility_org_tld(mcp_server):
    """.org TLD fallback scores 0.6 / medium."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://unknown-org.org/page"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.6
    assert data["label"] == "medium"


async def test_credibility_com_tld(mcp_server):
    """.com TLD fallback scores 0.5 / medium."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://unknown-site.com/page"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.5
    assert data["label"] == "medium"


async def test_credibility_unknown_tld(mcp_server):
    """Unknown TLD fallback scores 0.4 / medium."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://example.museum/exhibit"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.4
    assert data["label"] == "medium"


# ---------------------------------------------------------------------------
# check_credibility — hostname parsing edge cases
# ---------------------------------------------------------------------------

async def test_credibility_www_stripped(mcp_server):
    """www. prefix is stripped before domain lookup."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://www.arxiv.org/abs/123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["reason"] == "Known research publisher"


async def test_credibility_port_and_path_ignored(mcp_server):
    """Port and path are ignored; only hostname is used for scoring."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://arxiv.org:8080/abs/123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
```

- [ ] **Step 2: Run tests — all should fail (server.py doesn't exist yet)**

```bash
pytest mcp_tools/citation_checker/tests/test_server.py -v 2>&1 | head -30
```

Expected: errors like `ModuleNotFoundError: No module named 'mcp_tools.citation_checker.server'`

### Step 3: Implement `server.py` (credibility only)

- [ ] **Create `mcp_tools/citation_checker/server.py`**

```python
# mcp_tools/citation_checker/server.py
import json
import time
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP
from mcp.shared.exceptions import McpError, ErrorData
from mcp.types import INVALID_PARAMS

mcp = FastMCP("citation-checker-tool")

# ---------------------------------------------------------------------------
# Domain sets — checked in tier order (first match wins)
# ---------------------------------------------------------------------------

RESEARCH_DOMAINS = {
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "nature.com",
    "science.org", "springer.com", "wiley.com", "cell.com", "nejm.org",
    "thelancet.com", "bmj.com", "plos.org", "jstor.org",
    "semanticscholar.org", "scholar.google.com", "acm.org", "ieee.org",
    "ssrn.com", "researchgate.net", "biorxiv.org", "medrxiv.org",
    "nih.gov", "ncbi.nlm.nih.gov", "sciencedirect.com", "tandfonline.com",
}

CREDIBLE_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "who.int", "cdc.gov",
}

BLOG_HOST_DOMAINS = {
    "wordpress.com", "blogspot.com", "medium.com", "substack.com",
    "tumblr.com", "wix.com", "weebly.com",
}

URL_SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "buff.ly", "short.io",
}

LOW_CREDIBILITY_TLDS = {".click", ".biz", ".info", ".xyz", ".tk", ".ml", ".ga", ".cf"}

TLD_SCORES: dict[str, tuple[float, str, str]] = {
    ".edu": (0.85, "high", "Educational institution domain"),
    ".gov": (0.85, "high", "Government domain"),
    ".org": (0.6, "medium", "Non-profit/organisation domain"),
    ".com": (0.5, "medium", "Commercial domain"),
    ".net": (0.5, "medium", "Commercial domain"),
}
_DEFAULT_TLD_SCORE: tuple[float, str, str] = (0.4, "medium", "Unknown TLD")


def _score_url(url: str) -> tuple[float, str, str]:
    hostname = urlparse(url).hostname or ""
    domain = hostname[4:] if hostname.startswith("www.") else hostname
    tld = ("." + domain.rsplit(".", 1)[-1]) if "." in domain else ""

    if domain in RESEARCH_DOMAINS:
        return (0.9, "high", "Known research publisher")
    if domain in CREDIBLE_NEWS_DOMAINS:
        return (0.9, "high", "Known credible news/health source")
    if domain in BLOG_HOST_DOMAINS:
        return (0.2, "low", "Free blog host")
    if domain in URL_SHORTENER_DOMAINS:
        return (0.2, "low", "URL shortener")
    if tld in LOW_CREDIBILITY_TLDS:
        return (0.1, "low", "Low-credibility TLD")
    return TLD_SCORES.get(tld, _DEFAULT_TLD_SCORE)


@mcp.tool
async def check_credibility(url: str) -> str:
    """Score a URL's credibility using offline domain and TLD heuristics. No HTTP calls."""
    if not url or not url.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="url must not be empty"))
    hostname = urlparse(url).hostname
    if not hostname:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message=f"Could not parse hostname from URL: {url!r}. Ensure a scheme prefix is included (e.g. https://).",
        ))
    score, label, reason = _score_url(url)
    return json.dumps({"url": url, "score": score, "label": label, "reason": reason})
```

- [ ] **Step 4: Run credibility tests — all 16 should pass**

```bash
pytest mcp_tools/citation_checker/tests/test_server.py -v
```

Expected: 16 passed, 0 failed

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/citation_checker/server.py \
        mcp_tools/citation_checker/tests/test_server.py
git commit -m "feat: add check_credibility tool with 16 unit tests"
```

---

## Task 3: `check_reachability` — TDD

**Files:**
- Modify: `mcp_tools/citation_checker/tests/test_server.py` (append 9 tests)
- Modify: `mcp_tools/citation_checker/server.py` (add `check_reachability` tool)

Write all 9 reachability tests first (they will fail), then add the implementation.

### Step 1: Write the failing tests

- [ ] **Append reachability tests to `mcp_tools/citation_checker/tests/test_server.py`**

Add the following at the end of the file:

```python
# ---------------------------------------------------------------------------
# check_reachability — input validation
# ---------------------------------------------------------------------------

async def test_reachability_empty_url_raises(mcp_server):
    """Empty url raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_reachability", {"url": ""})


async def test_reachability_non_http_scheme_raises(mcp_server):
    """Non-http/https scheme (e.g. ftp://) raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_reachability", {"url": "ftp://example.com"})


async def test_reachability_empty_hostname_raises(mcp_server):
    """URL with empty hostname after scheme (e.g. https:///path) raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_reachability", {"url": "https:///path"})


# ---------------------------------------------------------------------------
# check_reachability — happy paths
# ---------------------------------------------------------------------------

async def test_reachability_happy_path(mcp_server):
    """Successful HEAD returns reachable=true with status_code, latency_ms, final_url."""
    with respx.mock:
        respx.head("https://arxiv.org/").mock(return_value=httpx.Response(200))
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://arxiv.org/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert data["status_code"] == 200
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0
    assert data["final_url"] == "https://arxiv.org/"


async def test_reachability_404_is_reachable(mcp_server):
    """404 response counts as reachable=true (server responded)."""
    with respx.mock:
        respx.head("https://example.com/missing").mock(return_value=httpx.Response(404))
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://example.com/missing"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert data["status_code"] == 404


async def test_reachability_redirect_final_url(mcp_server):
    """Redirects are followed; final_url reflects the resolved URL."""
    with respx.mock:
        respx.head("http://old.example.com/").mock(
            return_value=httpx.Response(301, headers={"location": "https://new.example.com/"})
        )
        respx.head("https://new.example.com/").mock(return_value=httpx.Response(200))
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "http://old.example.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert data["final_url"] == "https://new.example.com/"


# ---------------------------------------------------------------------------
# check_reachability — network failures → reachable=false
# ---------------------------------------------------------------------------

async def test_reachability_timeout_returns_unreachable(mcp_server):
    """Timeout returns reachable=false with all null fields."""
    with respx.mock:
        respx.head("https://slow.example.com/").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://slow.example.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is False
    assert data["status_code"] is None
    assert data["latency_ms"] is None
    assert data["final_url"] is None


async def test_reachability_connect_error_returns_unreachable(mcp_server):
    """ConnectError (DNS failure, refused) returns reachable=false."""
    with respx.mock:
        respx.head("https://unreachable.example.com/").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://unreachable.example.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is False
    assert data["status_code"] is None


async def test_reachability_too_many_redirects_returns_unreachable(mcp_server):
    """TooManyRedirects (httpx.HTTPError subclass) returns reachable=false."""
    req = httpx.Request("HEAD", "https://redirect-loop.com/")
    with respx.mock:
        respx.head("https://redirect-loop.com/").mock(
            side_effect=httpx.TooManyRedirects("too many redirects", request=req)
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://redirect-loop.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is False
    assert data["status_code"] is None
```

- [ ] **Step 2: Run tests — the 9 new tests should fail (tool not implemented yet)**

```bash
pytest mcp_tools/citation_checker/tests/test_server.py -v -k "reachability"
```

Expected: 9 failures like `ToolError: Tool 'check_reachability' not found`

### Step 3: Implement `check_reachability`

- [ ] **Append `check_reachability` to `mcp_tools/citation_checker/server.py`**

Add the following at the end of the file (after `check_credibility`):

```python
@mcp.tool
async def check_reachability(url: str) -> str:
    """Check if a URL is reachable via a single HTTP HEAD request."""
    if not url or not url.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="url must not be empty"))
    if not url.startswith("http://") and not url.startswith("https://"):
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="url must start with http:// or https://",
        ))
    hostname = urlparse(url).hostname
    if not hostname:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message=f"Could not parse hostname from URL: {url!r}",
        ))

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.head(url)
        latency_ms = round((time.monotonic() - start) * 1000)
        return json.dumps({
            "url": url,
            "reachable": True,
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "final_url": str(resp.url),
        })
    except httpx.HTTPError:
        return json.dumps({
            "url": url,
            "reachable": False,
            "status_code": None,
            "latency_ms": None,
            "final_url": None,
        })
```

- [ ] **Step 4: Run all unit tests — all 25 should pass**

```bash
pytest mcp_tools/citation_checker/tests/test_server.py -v
```

Expected: 25 passed, 0 failed

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/citation_checker/server.py \
        mcp_tools/citation_checker/tests/test_server.py
git commit -m "feat: add check_reachability tool with 9 unit tests"
```

---

## Task 4: Integration test

**Files:**
- Create: `mcp_tools/citation_checker/tests/test_integration.py`

This is a scaffold/test-only task. Single combined review pass if needed.

- [ ] **Step 1: Create `mcp_tools/citation_checker/tests/test_integration.py`**

```python
# mcp_tools/citation_checker/tests/test_integration.py
import json
import socket
import pytest
from fastmcp import Client

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def skip_if_no_network():
    """Auto-skip this test module if the network is unavailable."""
    try:
        socket.create_connection(("arxiv.org", 443), timeout=3)
    except OSError:
        pytest.skip("Network unavailable")


@pytest.fixture
def mcp_server():
    from mcp_tools.citation_checker.server import mcp
    return mcp


async def test_check_reachability_live(mcp_server):
    """Live HEAD request to arxiv.org — skipped automatically if offline."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_reachability", {"url": "https://arxiv.org/"})

    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert isinstance(data["status_code"], int)
    assert data["status_code"] > 0
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0
    assert data["final_url"] is not None
```

- [ ] **Step 2: Run the integration test (requires network)**

```bash
pytest mcp_tools/citation_checker/tests/test_integration.py -v
```

Expected: 1 passed

- [ ] **Step 3: Run the full test suite to confirm nothing broken**

```bash
pytest mcp_tools/citation_checker/ -v
```

Expected: 26 passed (25 unit + 1 integration)

- [ ] **Step 4: Commit**

```bash
git add mcp_tools/citation_checker/tests/test_integration.py
git commit -m "feat: add citation_checker integration test"
```

---

## Done

After all tasks complete, run the full suite one final time:

```bash
pytest mcp_tools/citation_checker/ -v
```

Expected: 26 passed, 0 failed.
