# Citation Checker MCP Tool Design

**Goal:** Build a FastMCP tool server that checks the credibility and reachability of citation URLs, to be consumed by research and RAG agents.

**Architecture:** Thin MCP tool layer — two tools, no external APIs, no required env vars. Mirrors the `web_search`, `vector_db`, and `file_reader` tool patterns exactly.

**Tech Stack:** FastMCP 2.x, httpx, python-dotenv, pytest + pytest-asyncio + respx

---

## File Structure

```
mcp_tools/citation_checker/
├── server.py          # FastMCP instance + tool logic (~130 lines)
├── main.py            # load_dotenv, mcp.run(port=9004)
├── requirements.txt   # dependencies
├── pytest.ini         # asyncio_mode = auto
├── __init__.py
└── tests/
    ├── __init__.py
    ├── test_server.py      # unit tests (~20 tests, all mocked)
    └── test_integration.py # live reachability test (skipped if no network)
```

---

## `main.py`

```python
import os, sys
from dotenv import load_dotenv

load_dotenv()

from mcp_tools.citation_checker.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9004)
```

---

## Tools

### `check_credibility`

Scores a URL's credibility using offline domain and TLD heuristics. No HTTP calls.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `url` | `str` | required | non-empty; must be parseable as a URL with a valid hostname |

**Response shape:**
```json
{
  "url": "https://arxiv.org/abs/2301.00001",
  "score": 0.9,
  "label": "high",
  "reason": "Known research publisher"
}
```

`label` values: `"high"` (score ≥ 0.7), `"medium"` (0.4 ≤ score < 0.7), `"low"` (score < 0.4)

---

### `check_reachability`

Sends a HEAD request to a URL and reports whether it is reachable, along with status code, latency, and final URL after redirects.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `url` | `str` | required | non-empty; must start with `http://` or `https://` |

**Response shape (reachable):**
```json
{
  "url": "https://arxiv.org/abs/2301.00001",
  "reachable": true,
  "status_code": 200,
  "latency_ms": 142,
  "final_url": "https://arxiv.org/abs/2301.00001"
}
```

**Response shape (unreachable):**
```json
{
  "url": "https://example-dead-link.com/paper",
  "reachable": false,
  "status_code": null,
  "latency_ms": null,
  "final_url": null
}
```

No `McpError` is raised for unreachable URLs — the tool succeeds and reports the result. `McpError(INVALID_PARAMS)` is raised only for malformed input. No retries — reachability is a one-shot check.

---

## Internal Structure (`server.py`)

```
FastMCP("citation-checker-tool")
│
├── HIGH_CREDIBILITY_DOMAINS: set[str]
│     — exact hostname matches (www. stripped before lookup)
│     — research: arxiv.org, pubmed.ncbi.nlm.nih.gov, nature.com,
│       science.org, springer.com, wiley.com, cell.com, nejm.org,
│       thelancet.com, bmj.com, plos.org, jstor.org,
│       semanticscholar.org, scholar.google.com, acm.org, ieee.org,
│       ssrn.com, researchgate.net, biorxiv.org, medrxiv.org,
│       nih.gov, ncbi.nlm.nih.gov, sciencedirect.com, tandfonline.com
│     — general: reuters.com, apnews.com, bbc.com, who.int, cdc.gov
│     — score: 0.9, label: "high", reason: "Known research publisher"
│       or "Known credible news/health source"
│
├── LOW_CREDIBILITY_DOMAINS: set[str]
│     — free blog hosts: wordpress.com, blogspot.com, medium.com,
│       substack.com, tumblr.com, wix.com, weebly.com
│     — URL shorteners: bit.ly, tinyurl.com, t.co, goo.gl,
│       ow.ly, buff.ly, short.io
│     — score: 0.2, label: "low", reason: "Free blog host" or "URL shortener"
│
├── LOW_CREDIBILITY_TLDS: set[str]
│     — {".click", ".biz", ".info", ".xyz", ".tk", ".ml", ".ga", ".cf"}
│     — score: 0.1, label: "low", reason: "Low-credibility TLD"
│
├── TLD_SCORES: dict[str, tuple[float, str, str]]
│     — ".edu" → (0.85, "high", "Educational institution domain")
│     — ".gov" → (0.85, "high", "Government domain")
│     — ".org" → (0.6, "medium", "Non-profit/organisation domain")
│     — ".com" → (0.5, "medium", "Commercial domain")
│     — ".net" → (0.5, "medium", "Commercial domain")
│     — default → (0.4, "medium", "Unknown TLD")
│
├── _score_url(url: str) -> tuple[float, str, str]
│     — parse hostname via urllib.parse.urlparse
│     — strip leading "www."
│     — check tiers in order:
│         1. domain in HIGH_CREDIBILITY_DOMAINS → (0.9, "high", reason)
│         2. domain in LOW_CREDIBILITY_DOMAINS → (0.2, "low", reason)
│         3. TLD suffix in LOW_CREDIBILITY_TLDS → (0.1, "low", reason)
│         4. TLD_SCORES lookup by suffix → fallback (0.4, "medium", "Unknown TLD")
│
└── check_credibility(url) -> str (JSON)
│     ├── validate: url non-empty → INVALID_PARAMS
│     ├── parse hostname; empty hostname → INVALID_PARAMS
│     ├── call _score_url(url)
│     └── return JSON {url, score, label, reason}
│
└── check_reachability(url) -> str (JSON)
      ├── validate: url non-empty → INVALID_PARAMS
      ├── validate: url starts with "http://" or "https://" → INVALID_PARAMS
      ├── record start time
      ├── httpx.AsyncClient(follow_redirects=True, timeout=10.0)
      │     HEAD request to url
      │     on success: reachable=True, status_code, latency_ms, final_url=str(resp.url)
      │     on httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError:
      │           reachable=False, status_code=null, latency_ms=null, final_url=null
      └── return JSON {url, reachable, status_code, latency_ms, final_url}
```

---

## Credibility Tiers (Summary)

| Tier | Condition | Score | Label |
|---|---|---|---|
| 1 — Known high | domain in HIGH_CREDIBILITY_DOMAINS | 0.9 | high |
| 2 — Known low (domain) | domain in LOW_CREDIBILITY_DOMAINS | 0.2 | low |
| 3 — Known low (TLD) | TLD suffix in LOW_CREDIBILITY_TLDS | 0.1 | low |
| 4 — TLD fallback .edu/.gov | TLD is .edu or .gov | 0.85 | high |
| 4 — TLD fallback .org | TLD is .org | 0.6 | medium |
| 4 — TLD fallback .com/.net | TLD is .com or .net | 0.5 | medium |
| 4 — TLD fallback default | any other TLD | 0.4 | medium |

---

## Error Handling

| Condition | Code |
|---|---|
| Empty `url` | `INVALID_PARAMS` |
| Unparseable hostname in `check_credibility` | `INVALID_PARAMS` |
| Non-http/https scheme in `check_reachability` | `INVALID_PARAMS` |
| Network failure in `check_reachability` | Returns `reachable: false` (no McpError) |

---

## Environment Variables

None required. The tool works without any API keys.

---

## Testing

### Unit tests (`test_server.py`, ~20 tests)

All HTTP calls mocked with respx. Uses FastMCP `Client` + pytest-asyncio. No real network calls.

| Test | Verifies |
|---|---|
| Empty `url` raises `ToolError` (check_credibility) | input validation |
| Empty `url` raises `ToolError` (check_reachability) | input validation |
| Non-http scheme raises `ToolError` (check_reachability) | scheme validation |
| Unparseable URL hostname raises `ToolError` | hostname validation |
| Known research domain (arxiv.org) → score 0.9, label "high" | tier 1 match |
| Known credible news domain (reuters.com) → score 0.9, label "high" | tier 1 match |
| Free blog host (wordpress.com) → score 0.2, label "low" | tier 2 match |
| URL shortener (bit.ly) → score 0.2, label "low" | tier 2 match |
| Low-credibility TLD (.xyz) → score 0.1, label "low" | tier 3 match |
| .edu TLD fallback → score 0.85, label "high" | tier 4 TLD match |
| .gov TLD fallback → score 0.85, label "high" | tier 4 TLD match |
| .org TLD fallback → score 0.6, label "medium" | tier 4 TLD match |
| .com TLD fallback → score 0.5, label "medium" | tier 4 TLD match |
| Unknown TLD fallback → score 0.4, label "medium" | tier 4 default |
| www. prefix stripped before lookup | www-stripping |
| Reachability happy path → reachable=true, status_code, latency_ms, final_url | reachability |
| Redirect followed → final_url differs from input url | redirect tracking |
| Timeout → reachable=false, all nulls | network failure |
| ConnectError → reachable=false, all nulls | network failure |
| HTTPError → reachable=false, all nulls | network failure |

### Integration test (`test_integration.py`, 1 test)

Calls `check_reachability` against a real URL (`https://arxiv.org`). Skipped if network unavailable. Asserts `reachable=true` and `status_code` is a positive integer.
