<!-- Generated: 2026-04-11 | Week 4+5 complete -->

# MCP Tool Servers

All 4 MCP tool servers are complete and stable. They communicate via FastMCP HTTP transport at `{host}:{port}/mcp` with A2A agents and upstream tools. No changes from Week 3 → Week 4+5 (tools remain stable; architecture migrated to ADK above them).

---

## web_search ✅ (port 9001)

**Caller**: `agents/web_research/mcp_client.py` → `agents/web_research/agent.py` (CrewAI agent with search_web tool)

```
main.py    → validate TAVILY_API_KEY → mcp.run(transport="http", port=9001)
server.py  → FastMCP("web-search-tool")
             └── search_web(query, num_results=5, search_depth="basic", include_answer=False) → str (JSON)
                   ├── validate: query non-empty, num_results 1–10
                   ├── _call_tavily(payload) — 3 retry attempts, [1s, 2s] backoff
                   │     ├── retry: 429, 500, 502, 503, 504, TimeoutException, ConnectError
                   │     └── raise immediately: 401, 400, HTTPStatusError
                   └── filter results: drop if url=null or title missing
```

**FastMCP HTTP call** (from agent mcp_client):
```python
async with Client("http://localhost:9001/mcp") as client:
    result = await client.call_tool("search_web", {"query": "...", "num_results": 5})
    # result.content[0].text → JSON string
```

**Response**:
```json
{
  "query": "...",
  "results": [{"title": "...", "url": "...", "content": "...", "score": 0.95}],
  "answer": "..."  // optional
}
```

**Key files**:
- `mcp_tools/web_search/server.py` (99 lines, retry + filtering logic)
- `mcp_tools/web_search/main.py` (15 lines, startup validation)
- `mcp_tools/web_search/tests/test_server.py` (17 unit tests)
- `mcp_tools/web_search/tests/test_integration.py` (1 live test)

**Env vars**: `TAVILY_API_KEY` (required)

---

## vector_db ✅ (port 9002)

**Caller**: `agents/rag/mcp_client.py` → `agents/rag/agent.py` (LlamaIndex agent with document search tools)

```
main.py    → validate QDRANT_URL + OPENAI_API_KEY → mcp.run(transport="http", port=9002)
server.py  → FastMCP("vector-db-tool")
             ├── ingest_document(title, content, url, collection="documents", chunk_size=1000, overlap=200) → str (JSON)
             │     ├── validate: non-empty strings, chunk_size 1–5000, overlap 0–500, overlap < chunk_size
             │     ├── _chunk_text(content, chunk_size, overlap) — character-based sliding window
             │     ├── _get_embedding(chunk) — OpenAI text-embedding-3-small (1536-dim), 3 attempts, [1s, 2s] backoff
             │     ├── ensure collection exists (create if missing, cosine distance, 1536-dim)
             │     └── qdrant.upsert(points) — each point: uuid4 id, vector, payload{document_id, title, url, content, chunk_index}
             └── search_documents(query, collection="documents", num_results=5) → str (JSON)
                   ├── validate: non-empty query, num_results 1–20
                   ├── collection_exists() check — raise McpError if missing (no embedding call)
                   ├── _get_embedding(query) — same retry pattern
                   └── qdrant.search(collection, query_vector, limit=num_results) — 3 attempts, [1s, 2s] backoff
```

**FastMCP HTTP call** (from agent mcp_client):
```python
async with Client("http://localhost:9002/mcp") as client:
    result = await client.call_tool("search_documents", {"query": "...", "num_results": 5})
    # result.content[0].text → JSON string
```

**Responses**:
```json
{
  "collection": "documents",
  "document_id": "<uuid4>",
  "chunks_stored": 4,
  "title": "..."
}

{
  "query": "...",
  "collection": "documents",
  "results": [{"title": "...", "url": "...", "content": "...", "score": 0.87}]
}
```

**Key files**:
- `mcp_tools/vector_db/server.py` (170 lines, chunking + embeddings + retry)
- `mcp_tools/vector_db/main.py` (startup validation)
- `mcp_tools/vector_db/tests/test_server.py` (25 unit tests)
- `mcp_tools/vector_db/tests/test_integration.py` (1 live test)

**Env vars**: `QDRANT_URL` (required), `OPENAI_API_KEY` (required)

---

## file_reader ✅ (port 9003)

**Caller**: `agents/summariser/mcp_client.py` → `agents/summariser/agent.py` (reads PDF/text files for synthesis)

```
main.py    → load_dotenv() → mcp.run(transport="http", host="0.0.0.0", port=9003)
server.py  → FastMCP("file-reader-tool")
             └── read_file(source, start_page=1, end_page=None) → str (JSON)
                   ├── validate: source non-empty, not http://, start_page ≥ 1, end_page ≥ start_page
                   ├── _detect_file_type(source) — .pdf → pdf; .txt/.md → text; no-ext URL → text; else INVALID_PARAMS
                   ├── local path: _check_path_allowed(source) — if FILE_READER_BASE_DIR set, reject traversal outside it
                   ├── _read_local(path) → bytes via asyncio.to_thread — FileNotFoundError/PermissionError → INVALID_PARAMS
                   ├── _fetch_remote(url) → bytes — RETRYABLE_STATUS {429,500,502,503,504}, 3 attempts, [1s,2s] backoff
                   ├── PDF path: asyncio.to_thread(_parse_pdf) → page_count, get_text(), metadata{title,author}
                   │     ├── end_page clamped to page_count; pages_read: "N" or "start-end" from resolved values
                   │     └── doc.close() called in finally block (explicit resource release)
                   └── text path: bytes.decode("utf-8", errors="replace") → null metadata
```

**FastMCP HTTP call** (from agent mcp_client):
```python
async with Client("http://localhost:9003/mcp") as client:
    result = await client.call_tool("read_file", {"source": "path/to/file.pdf"})
    # result.content[0].text → JSON string
```

**Response**:
```json
{
  "source": "path/to/file.pdf",
  "file_type": "pdf",
  "text": "...",
  "metadata": {
    "title": "...",
    "author": "...",
    "page_count": 10,
    "pages_read": "1-10"
  }
}
```

**Key files**:
- `mcp_tools/file_reader/server.py` (193 lines, path allowlist + PDF parsing)
- `mcp_tools/file_reader/main.py` (binds to 0.0.0.0:9003)
- `mcp_tools/file_reader/tests/test_server.py` (24 unit tests)
- `mcp_tools/file_reader/tests/test_integration.py` (1 integration test)
- `mcp_tools/file_reader/tests/fixtures/sample.pdf` (2-page test fixture)

**Env vars**: `FILE_READER_BASE_DIR` (optional, restricts local path access)

---

## citation_checker ✅ (port 9004)

**Caller**: `agents/summariser/mcp_client.py` → `agents/summariser/agent.py` (validates source credibility + reachability)

```
main.py    → load_dotenv() → mcp.run(transport="http", host="0.0.0.0", port=9004)
server.py  → FastMCP("citation-checker-tool")
             ├── check_credibility(url) → str (JSON)
             │     ├── validate: url non-empty, can be parsed to hostname
             │     ├── _score_url(url) — tier checks (first match wins):
             │     │     ├── RESEARCH_DOMAINS {arxiv.org, pubmed.ncbi.nlm.nih.gov, nature.com, ...} → (0.9, "high")
             │     │     ├── CREDIBLE_NEWS_DOMAINS {reuters.com, apnews.com, bbc.com, who.int, cdc.gov} → (0.9, "high")
             │     │     ├── BLOG_HOST_DOMAINS {wordpress.com, blogspot.com, medium.com, ...} → (0.2, "low")
             │     │     ├── URL_SHORTENER_DOMAINS {bit.ly, tinyurl.com, t.co, ...} → (0.2, "low")
             │     │     ├── LOW_CREDIBILITY_TLDS {.click, .biz, .info, .xyz, .tk, .ml, .ga, .cf} → (0.1, "low")
             │     │     └── TLD_SCORES {.edu→0.85, .gov→0.85, .org→0.6, .com→0.5, .net→0.5, default→0.4}
             │     └── no HTTP calls — purely heuristic
             └── check_reachability(url) → str (JSON)
                   ├── validate: url non-empty, starts with http:// or https://, can be parsed to hostname
                   ├── httpx.AsyncClient(follow_redirects=True, timeout=10.0)
                   ├── HEAD request + latency measurement via time.monotonic()
                   └── return reachable + status_code + latency_ms + final_url (or all null if unreachable)
```

**FastMCP HTTP calls** (from agent mcp_client):
```python
async with Client("http://localhost:9004/mcp") as client:
    cred = await client.call_tool("check_credibility", {"url": "https://example.com"})
    reach = await client.call_tool("check_reachability", {"url": "https://example.com"})
    # results → JSON strings
```

**Responses**:
```json
{
  "url": "https://arxiv.org/abs/2024-01234",
  "score": 0.9,
  "label": "high",
  "reason": "Known research publisher"
}

{
  "url": "https://example.com",
  "reachable": true,
  "status_code": 200,
  "latency_ms": 145,
  "final_url": "https://www.example.com"
}

{
  "url": "https://dead.link.com",
  "reachable": false,
  "status_code": null,
  "latency_ms": null,
  "final_url": null
}
```

**Key files**:
- `mcp_tools/citation_checker/server.py` (121 lines, domain/TLD scoring + reachability)
- `mcp_tools/citation_checker/main.py` (binds to 0.0.0.0:9004)
- `mcp_tools/citation_checker/tests/test_server.py` (27 unit tests)
- `mcp_tools/citation_checker/tests/test_integration.py` (1 live integration test)

**Env vars**: None required (purely offline heuristics + HTTP HEAD)

---

## Test Coverage Summary

| Tool | Unit Tests | Integration | Total | Coverage |
|------|-----------|-------------|-------|----------|
| web_search | 17 | 1 | 18 | ~95% |
| vector_db | 25 | 1 | 26 | ~92% |
| file_reader | 24 | 1 | 25 | ~90% |
| citation_checker | 27 | 1 | 28 | ~94% |
| **Total** | **93** | **4** | **97** | |

**Run all tests**:
```bash
pytest mcp_tools/ -v --tb=short
```

**Run specific tool tests**:
```bash
pytest mcp_tools/web_search/tests/ -v
```
