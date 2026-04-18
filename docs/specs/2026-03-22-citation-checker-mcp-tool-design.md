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
    ├── test_server.py      # unit tests (~24 tests, all mocked)
    └── test_integration.py # live reachability test (skipped if no network)
```

---

## `main.py`

```python
from dotenv import load_dotenv

load_dotenv()

from mcp_tools.citation_checker.server import mcp  # noqa: E402

if __name__ == "__main__":
    # Binds to 0.0.0.0 — deploy behind an authenticated proxy or in a network-isolated container.
    mcp.run(transport="http", host="0.0.0.0", port=9004)
```

---

## Tools

### `check_credibility`

Scores a URL's credibility using offline domain and TLD heuristics. No HTTP calls. Any URL scheme is accepted (scoring is domain-based, not scheme-based). Hostname is extracted via `urllib.parse.urlparse` — port and path are ignored.

**Important:** A schemeless string like `"arxiv.org/abs/123"` (no `://`) will produce an empty hostname from `urlparse` and must raise `INVALID_PARAMS`. Callers must pass a fully-formed URL with a scheme.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `url` | `str` | required | non-empty; must yield a non-empty hostname when parsed (requires scheme prefix) |

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

Sends a single HEAD request to a URL and reports whether it is reachable, along with status code, latency, and final URL after redirects. No retries — reachability is a one-shot check.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `url` | `str` | required | non-empty; must start with `http://` or `https://` |

**Reachability definition:** Any response from the server (including 4xx and 5xx) counts as `reachable: true` with the corresponding `status_code`. Only exceptions raised by `httpx` (including `TimeoutException`, `ConnectError`, `TooManyRedirects`, and all other `httpx` errors) result in `reachable: false`. This intentionally treats all httpx failures uniformly as "unreachable."

**`latency_ms`** is measured via `time.monotonic()` (wraps the full client call including redirect hops), computed as `round((end - start) * 1000)` — an integer. `response.elapsed` is not used.

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

**Response shape (unreachable — any httpx exception):**
```json
{
  "url": "https://example-dead-link.com/paper",
  "reachable": false,
  "status_code": null,
  "latency_ms": null,
  "final_url": null
}
```

No `McpError` is raised for unreachable URLs — the tool succeeds and reports the result. `McpError(INVALID_PARAMS)` is raised only for malformed input. Both tools return `json.dumps(result)` with no indentation (same as sister tools).

---

## Internal Structure (`server.py`)

```
FastMCP("citation-checker-tool")
│
├── RESEARCH_DOMAINS: set[str]
│     — exact hostname matches (www. stripped before lookup)
│     — arxiv.org, pubmed.ncbi.nlm.nih.gov, nature.com,
│       science.org, springer.com, wiley.com, cell.com, nejm.org,
│       thelancet.com, bmj.com, plos.org, jstor.org,
│       semanticscholar.org, scholar.google.com, acm.org, ieee.org,
│       ssrn.com, researchgate.net, biorxiv.org, medrxiv.org,
│       nih.gov, ncbi.nlm.nih.gov, sciencedirect.com, tandfonline.com
│     — score: 0.9, label: "high", reason: "Known research publisher"
│
├── CREDIBLE_NEWS_DOMAINS: set[str]
│     — reuters.com, apnews.com, bbc.com, who.int, cdc.gov
│     — score: 0.9, label: "high", reason: "Known credible news/health source"
│
├── BLOG_HOST_DOMAINS: set[str]
│     — wordpress.com, blogspot.com, medium.com, substack.com,
│       tumblr.com, wix.com, weebly.com
│     — score: 0.2, label: "low", reason: "Free blog host"
│
├── URL_SHORTENER_DOMAINS: set[str]
│     — bit.ly, tinyurl.com, t.co, goo.gl, ow.ly, buff.ly, short.io
│     — score: 0.2, label: "low", reason: "URL shortener"
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
│     — parse hostname via urllib.parse.urlparse (port and path ignored)
│     — strip leading "www."
│     — check tiers in order:
│         1. domain in RESEARCH_DOMAINS → (0.9, "high", "Known research publisher")
│         2. domain in CREDIBLE_NEWS_DOMAINS → (0.9, "high", "Known credible news/health source")
│         3. domain in BLOG_HOST_DOMAINS → (0.2, "low", "Free blog host")
│         4. domain in URL_SHORTENER_DOMAINS → (0.2, "low", "URL shortener")
│         5. TLD suffix in LOW_CREDIBILITY_TLDS → (0.1, "low", "Low-credibility TLD")
│         6. TLD_SCORES lookup by suffix → fallback (0.4, "medium", "Unknown TLD")
│
├── check_credibility(url) -> str (JSON)
│     ├── validate: url non-empty → INVALID_PARAMS
│     ├── parse hostname via urlparse; empty hostname → INVALID_PARAMS
│     │     (schemeless strings like "arxiv.org/path" produce empty hostname)
│     ├── call _score_url(url)
│     └── return json.dumps({url, score, label, reason})
│
└── check_reachability(url) -> str (JSON)
      ├── validate: url non-empty → INVALID_PARAMS
      ├── validate: url starts with "http://" or "https://" → INVALID_PARAMS
      ├── validate: parsed hostname is non-empty → INVALID_PARAMS
      │     (catches malformed inputs like "https:///path")
      ├── start = time.monotonic()
      ├── async with httpx.AsyncClient(follow_redirects=True, timeout=10.0):
      │     resp = await client.head(url)
      │     on any HTTP response (including 4xx/5xx):
      │           reachable=True, status_code=resp.status_code,
      │           latency_ms=round((time.monotonic()-start)*1000),
      │           final_url=str(resp.url)
      │     except httpx.HTTPError (base class for all httpx exceptions, including TooManyRedirects):
      │           reachable=False, status_code=null, latency_ms=null, final_url=null
      └── return json.dumps({url, reachable, status_code, latency_ms, final_url})
```

---

## Credibility Tiers (Summary)

| Tier | Condition | Score | Label |
|---|---|---|---|
| 1 — Research domain | domain in RESEARCH_DOMAINS | 0.9 | high |
| 2 — News/health domain | domain in CREDIBLE_NEWS_DOMAINS | 0.9 | high |
| 3 — Blog host | domain in BLOG_HOST_DOMAINS | 0.2 | low |
| 4 — URL shortener | domain in URL_SHORTENER_DOMAINS | 0.2 | low |
| 5 — Low-credibility TLD | TLD suffix in LOW_CREDIBILITY_TLDS | 0.1 | low |
| 6 — TLD fallback .edu/.gov | TLD is .edu or .gov | 0.85 | high |
| 6 — TLD fallback .org | TLD is .org | 0.6 | medium |
| 6 — TLD fallback .com/.net | TLD is .com or .net | 0.5 | medium |
| 6 — TLD fallback default | any other TLD | 0.4 | medium |

---

## Error Handling

| Condition | Code |
|---|---|
| Empty `url` (either tool) | `INVALID_PARAMS` |
| Unparseable/empty hostname in `check_credibility` (including schemeless strings) | `INVALID_PARAMS` |
| Non-http/https scheme in `check_reachability` | `INVALID_PARAMS` |
| Empty hostname after scheme check in `check_reachability` (e.g. `https:///path`) | `INVALID_PARAMS` |
| Any httpx exception in `check_reachability` (timeout, DNS, TooManyRedirects, etc.) | Returns `reachable: false` (no McpError) |
| HTTP 4xx/5xx response in `check_reachability` | Returns `reachable: true` with status code |

---

## Environment Variables

None required. The tool works without any API keys.

---

## Testing

### Unit tests (`test_server.py`, ~24 tests)

All HTTP calls mocked with respx. Uses FastMCP `Client` + pytest-asyncio. No real network calls.

| Test | Input example | Verifies |
|---|---|---|
| Empty `url` raises `ToolError` (check_credibility) | `""` | input validation |
| Empty `url` raises `ToolError` (check_reachability) | `""` | input validation |
| Non-http scheme raises `ToolError` (check_reachability) | `"ftp://example.com"` | scheme validation |
| Schemeless string raises `ToolError` (check_credibility) | `"arxiv.org/abs/123"` | schemeless input |
| Unparseable/empty hostname raises `ToolError` (check_credibility) | `"not-a-url"` | hostname validation |
| Empty hostname raises `ToolError` (check_reachability) | `"https:///path"` | hostname validation |
| Non-http/https scheme accepted by check_credibility | `"ftp://arxiv.org/paper"` → score 0.9 | scheme-agnostic scoring |
| Known research domain → score 0.9, label "high", reason "Known research publisher" | `"https://arxiv.org/abs/123"` | tier 1 match |
| Known news domain → score 0.9, label "high", reason "Known credible news/health source" | `"https://reuters.com/article/x"` | tier 2 match |
| Free blog host → score 0.2, label "low", reason "Free blog host" | `"https://wordpress.com/post"` | tier 3 match |
| URL shortener → score 0.2, label "low", reason "URL shortener" | `"https://bit.ly/abc"` | tier 4 match |
| Low-credibility TLD → score 0.1, label "low" | `"https://example.xyz/page"` | tier 5 match |
| .edu TLD fallback → score 0.85, label "high" | `"https://mit.edu/paper"` | tier 6 TLD match |
| .gov TLD fallback → score 0.85, label "high" | `"https://nasa.gov/report"` | tier 6 TLD match |
| .org TLD fallback → score 0.6, label "medium" | `"https://unknown-org.org"` | tier 6 TLD match |
| .com TLD fallback → score 0.5, label "medium" | `"https://unknown-site.com"` | tier 6 TLD match |
| Unknown TLD fallback → score 0.4, label "medium" | `"https://example.museum"` | tier 6 default |
| www. prefix stripped before lookup | `"https://www.arxiv.org/abs/123"` → score 0.9 | www-stripping |
| URL with port/path — hostname extracted correctly | `"https://arxiv.org:8080/abs/123"` → score 0.9 | port/path ignored |
| Reachability happy path → reachable=true, status_code=200, latency_ms int, final_url set | `"https://arxiv.org"` | reachability success |
| 404 response → reachable=true, status_code=404 | `"https://example.com/missing"` | 4xx = reachable |
| Redirect followed → final_url differs from input | mock redirect | redirect tracking |
| Timeout → reachable=false, all nulls | mock TimeoutException | network failure |
| ConnectError → reachable=false, all nulls | mock ConnectError | network failure |
| TooManyRedirects → reachable=false, all nulls | mock TooManyRedirects | httpx catch-all |

### Integration test (`test_integration.py`, 1 test)

Calls `check_reachability` against a real URL (`https://arxiv.org`). Skipped if network unavailable. Asserts `reachable=true` and `status_code` is a positive integer.
