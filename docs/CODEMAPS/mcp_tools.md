<!-- Generated: 2026-03-21 | Files scanned: 8 | Token estimate: ~350 -->

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

## file_reader ⬜ (port 9003)
Tools: PDF/text parsing — wraps PyMuPDF

## citation_checker ⬜ (port 9004)
Tools: URL validation + credibility heuristics
