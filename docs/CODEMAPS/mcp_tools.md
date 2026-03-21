<!-- Generated: 2026-03-22 | Files scanned: 12 | Token estimate: ~480 -->

# MCP Tool Servers

## web_search ✅ (port 9001)

```
main.py  →  load_dotenv() → validate TAVILY_API_KEY → mcp.run(transport="http", port=9001)
server.py →  FastMCP("web-search-tool")
              └── search_web(query, num_results=5, search_depth="basic", include_answer=False) → str (JSON)
                    ├── validate: query non-empty, num_results 1–10
                    ├── _call_tavily(payload) — 3 attempts, backoff [1s, 2s]
                    │     ├── retry: 429, 500, 502, 503, 504, TimeoutException, ConnectError
                    │     └── raise immediately: 401, 400, HTTPStatusError
                    └── filter results: drop if url=null or title missing
```

**Response shape:**
```json
{"query": "...", "results": [{"title","url","content","score"}], "answer"?: "..."}
```

**Key files:**
- `mcp_tools/web_search/server.py` — tool logic, retry, filtering (99 lines)
- `mcp_tools/web_search/main.py` — entrypoint, startup validation (15 lines)
- `mcp_tools/web_search/tests/test_server.py` — 17 unit tests
- `mcp_tools/web_search/tests/test_integration.py` — 1 live test (skip if no key)

**Env vars:** `TAVILY_API_KEY` (required)

---

## vector_db ✅ (port 9002)

```
main.py  →  load_dotenv() → validate QDRANT_URL + OPENAI_API_KEY → mcp.run(transport="http", port=9002)
server.py →  FastMCP("vector-db-tool")
              ├── ingest_document(title, content, url, collection="documents", chunk_size=1000, overlap=200) → str (JSON)
              │     ├── validate: non-empty strings, chunk_size 1–5000, overlap 0–500, overlap < chunk_size
              │     ├── _chunk_text(content, chunk_size, overlap) — character-based sliding window
              │     ├── _get_embedding(chunk) — OpenAI text-embedding-3-small (1536-dim), 3 attempts, backoff [1s, 2s]
              │     ├── ensure collection exists (create if missing, cosine distance, 1536-dim)
              │     └── qdrant.upsert(points) — each point: uuid4 id, vector, payload{document_id, title, url, content, chunk_index}
              └── search_documents(query, collection="documents", num_results=5) → str (JSON)
                    ├── validate: non-empty query, num_results 1–20
                    ├── collection_exists() check — raise McpError immediately if missing (no embedding call)
                    ├── _get_embedding(query) — same retry pattern
                    └── qdrant.search(collection, query_vector, limit=num_results) — 3 attempts, backoff [1s, 2s]
```

**Response shapes:**
```json
{"collection": "...", "document_id": "<uuid4>", "chunks_stored": 4, "title": "..."}
{"query": "...", "collection": "...", "results": [{"title", "url", "content", "score"}]}
```

**Key files:**
- `mcp_tools/vector_db/server.py` — tool logic, chunking, embeddings, retry (~170 lines)
- `mcp_tools/vector_db/main.py` — entrypoint, startup validation
- `mcp_tools/vector_db/tests/test_server.py` — 25 unit tests
- `mcp_tools/vector_db/tests/test_integration.py` — 1 live test (skip if no keys)

**Env vars:** `QDRANT_URL` (required), `OPENAI_API_KEY` (required)

---

## file_reader ✅ (port 9003)

```
main.py  →  load_dotenv() → mcp.run(transport="http", host="0.0.0.0", port=9003)
server.py →  FastMCP("file-reader-tool")
              └── read_file(source, start_page=1, end_page=None) → str (JSON)
                    ├── validate: source non-empty, not http://, start_page ≥ 1, end_page ≥ start_page
                    ├── _detect_file_type(source) — .pdf → pdf; .txt/.md → text; no-ext URL → text; else INVALID_PARAMS
                    ├── local path: _check_path_allowed(source) — if FILE_READER_BASE_DIR set, reject traversal outside it
                    ├── _read_local(path) → bytes via asyncio.to_thread — FileNotFoundError/PermissionError → INVALID_PARAMS
                    ├── _fetch_remote(url) → bytes — RETRYABLE_STATUS {429,500,502,503,504}, 3 attempts, backoff [1s,2s]
                    ├── PDF path: asyncio.to_thread(_parse_pdf) → page_count, get_text(), metadata{title,author}
                    │     ├── end_page clamped to page_count; pages_read: "N" or "start-end" from resolved values
                    │     └── doc.close() called in finally block (explicit resource release)
                    └── text path: bytes.decode("utf-8", errors="replace") → null metadata
```

**Response shape:**
```json
{"source": "...", "file_type": "pdf|text", "text": "...", "metadata": {"title", "author", "page_count", "pages_read"}}
```

**Key files:**
- `mcp_tools/file_reader/server.py` — tool logic, path allowlist, PDF parsing (~193 lines)
- `mcp_tools/file_reader/main.py` — entrypoint, binds to 0.0.0.0:9003
- `mcp_tools/file_reader/tests/test_server.py` — 24 unit tests
- `mcp_tools/file_reader/tests/test_integration.py` — 1 integration test (no env vars required)
- `mcp_tools/file_reader/tests/fixtures/sample.pdf` — bundled 2-page test fixture

**Env vars:** `FILE_READER_BASE_DIR` (optional — restricts local path access to a subtree)

---

## citation_checker ⬜ (port 9004)
Tools: URL validation + credibility heuristics
