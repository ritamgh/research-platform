# Vector DB MCP Tool Design

**Goal:** Build a FastMCP tool server that wraps Qdrant for document ingestion and semantic search, to be consumed by the RAG agent and web_research agent.

**Architecture:** Thin MCP tool layer — `qdrant-client` + `openai` SDK directly, no framework abstractions. Mirrors the `web_search` tool pattern exactly. Qdrant runs as a remote server (Docker); the tool connects via `QDRANT_URL`.

**Tech Stack:** FastMCP 2.x, qdrant-client, openai (embeddings only), python-dotenv, pytest + pytest-asyncio

---

## File Structure

```
mcp_tools/vector_db/
├── server.py          # FastMCP instance + tool logic (~150 lines)
├── main.py            # load_dotenv, env validation, mcp.run(port=9002)
├── requirements.txt   # dependencies
├── pytest.ini         # asyncio_mode = auto
├── __init__.py
└── tests/
    ├── __init__.py
    ├── test_server.py      # unit tests (mocked Qdrant + OpenAI)
    └── test_integration.py # live test, skipped without QDRANT_URL + OPENAI_API_KEY
```

---

## `main.py`

Mirrors `web_search/main.py` exactly:

```python
import os, sys
from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("QDRANT_URL"):
    print("ERROR: QDRANT_URL environment variable is not set", file=sys.stderr)
    sys.exit(1)

if not os.environ.get("OPENAI_API_KEY"):
    print("ERROR: OPENAI_API_KEY environment variable is not set", file=sys.stderr)
    sys.exit(1)

from mcp_tools.vector_db.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9002)
```

---

## Tools

### `ingest_document`

Accepts a full document, chunks it, embeds each chunk via OpenAI, and upserts into Qdrant.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `title` | `str` | required | non-empty |
| `content` | `str` | required | non-empty |
| `url` | `str` | required | non-empty |
| `collection` | `str` | `"documents"` | non-empty |
| `chunk_size` | `int` | `1000` | 1–5000 chars |
| `overlap` | `int` | `200` | 0–500 chars, must be `< chunk_size` |

**Response shape:**
```json
{
  "collection": "documents",
  "document_id": "<uuid4>",
  "chunks_stored": 4,
  "title": "Example Article"
}
```

### `search_documents`

Embeds a query via OpenAI and performs a vector similarity search in Qdrant.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `query` | `str` | required | non-empty |
| `collection` | `str` | `"documents"` | non-empty |
| `num_results` | `int` | `5` | 1–20 |

**Response shape:**
```json
{
  "query": "...",
  "collection": "documents",
  "results": [
    {"title": "...", "url": "...", "content": "...chunk text...", "score": 0.91}
  ]
}
```

---

## Internal Structure (`server.py`)

```
FastMCP("vector-db-tool")
├── _get_qdrant_client() -> QdrantClient
│     — validates QDRANT_URL env var, raises McpError(INTERNAL_ERROR) if missing
├── _get_embedding(text) -> list[float]
│     — validates OPENAI_API_KEY, calls text-embedding-3-small (dim=1536)
│     — own retry loop: 3 attempts, backoff [1s, 2s]
│     — OpenAI 401 → raise immediately; 429/5xx → retry
├── _chunk_text(text, chunk_size, overlap) -> list[str]
│     — character-based splitter; guaranteed non-empty output (content shorter
│       than chunk_size returns a single chunk)
├── ingest_document(...) -> str (JSON)
│     ├── validate inputs (empty strings, chunk_size 1–5000, overlap 0–500,
│     │   overlap < chunk_size, num_results 1–20)
│     ├── generate document_id = uuid4()
│     ├── chunk content via _chunk_text
│     ├── embed each chunk via _get_embedding (independent retry per call)
│     ├── ensure collection exists:
│     │     if not client.collection_exists(collection):
│     │         client.create_collection(collection, vectors_config=VectorParams(size=1536, distance=Distance.COSINE))
│     ├── build list of PointStruct(id=uuid4(), vector=..., payload={document_id, title, url, content, chunk_index})
│     │     — each point gets its own uuid4() as its Qdrant point ID
│     └── client.upsert(collection, points) → return summary JSON
│           — upsert has its own retry loop: 3 attempts, backoff [1s, 2s]
└── search_documents(...) -> str (JSON)
      ├── validate inputs
      ├── embed query via _get_embedding
      ├── if not client.collection_exists(collection) → raise McpError(INVALID_REQUEST) immediately
      └── client.search(collection, query_vector, limit=num_results)
            — search has its own retry loop: 3 attempts, backoff [1s, 2s]
            → return results JSON
```

---

## Data Model

Each Qdrant point:

- **ID:** `uuid4()` — unique per point
- **Vector:** 1536-dim float list (`text-embedding-3-small`)
- **Payload:**

```python
{
    "document_id": "uuid4",   # same across all chunks of one ingest call
    "title": "...",
    "url": "https://source.com/article",
    "content": "...chunk text...",
    "chunk_index": 0,
}
```

**Chunking:** Character-based with configurable `chunk_size` (default 1000) and `overlap` (default 200). `overlap` must be strictly less than `chunk_size`. Content shorter than `chunk_size` returns a single chunk. No tokenizer dependency.

---

## Error Handling

| Condition | Code | Retry |
|---|---|---|
| `QDRANT_URL` not set | `INTERNAL_ERROR` | — |
| `OPENAI_API_KEY` not set | `INTERNAL_ERROR` | — |
| Empty `query`, `title`, `content`, `url`, or `collection` | `INVALID_PARAMS` | — |
| `chunk_size` out of range (1–5000) | `INVALID_PARAMS` | — |
| `overlap` out of range (0–500) or `overlap >= chunk_size` | `INVALID_PARAMS` | — |
| `num_results` out of range (1–20) | `INVALID_PARAMS` | — |
| OpenAI 401 auth failure | `INVALID_REQUEST` | No |
| OpenAI 429 / 5xx | `INTERNAL_ERROR` | 3 attempts, backoff [1s, 2s] |
| Qdrant connection error (upsert or search) | `INTERNAL_ERROR` | 3 attempts, backoff [1s, 2s] |
| Collection not found on `search_documents` | `INVALID_REQUEST` | No |

Each external call type has its own independent retry loop (embedding calls, upsert, search). Retry loops use `for attempt in range(3)` with `asyncio.sleep(BACKOFF_DELAYS[attempt - 1])` — same pattern as `web_search`. Tests patch `asyncio.sleep`.

---

## Environment Variables

| Var | Required | Purpose |
|---|---|---|
| `QDRANT_URL` | Yes | Remote Qdrant server URL (e.g. `http://localhost:6333`) |
| `OPENAI_API_KEY` | Yes | OpenAI embeddings API |

---

## Testing

### Unit tests (`test_server.py`, ~20 tests)

All Qdrant and OpenAI calls mocked. Uses `FastMCP Client` + `pytest-asyncio`, same pattern as `web_search`.

| Test | Verifies |
|---|---|
| Missing `QDRANT_URL` → `ToolError` | env validation |
| Missing `OPENAI_API_KEY` → `ToolError` | env validation |
| Successful ingest returns correct shape | happy path |
| `chunks_stored` matches expected chunk count | chunking math |
| Content shorter than `chunk_size` produces 1 chunk | chunking boundary |
| Ingest creates collection when it doesn't exist | collection auto-creation |
| Empty `content` raises without any external call | input validation |
| Empty `query` raises without any external call | input validation |
| `chunk_size=0` raises without external call | bounds check |
| `chunk_size=5001` raises without external call | bounds check |
| `overlap=chunk_size` raises without external call | overlap constraint |
| `num_results=0` raises without external call | bounds check |
| `num_results=21` raises without external call | bounds check |
| Successful search returns correct shape | happy path |
| Search on missing collection → `ToolError` immediately | no retry |
| OpenAI 401 → `ToolError` immediately (ingest) | no retry on auth |
| OpenAI 429 retries 3× then → `ToolError` | retry exhaustion |
| Qdrant connection error retries 3× then → `ToolError` | retry exhaustion |
| Qdrant connection error recovers on 3rd attempt | retry success |
| `collection` param routes to correct Qdrant collection | named collections |

### Integration test (`test_integration.py`, 1 test)

Auto-skips without `QDRANT_URL` + `OPENAI_API_KEY`. Ingests one document, searches for it, asserts a result is returned.
