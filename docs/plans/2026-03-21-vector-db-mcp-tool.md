# Vector DB MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastMCP server at port 9002 that exposes `ingest_document` and `search_documents` tools, wrapping Qdrant (remote server) for document storage and OpenAI `text-embedding-3-small` for embeddings.

**Architecture:** Mirrors `mcp_tools/web_search` exactly. `server.py` owns the FastMCP instance, tool definitions, helper functions, and retry loops. `main.py` validates both env vars at startup then runs the server. Tests use FastMCP's in-process `Client(mcp)` with `unittest.mock.patch` to mock `AsyncQdrantClient` and `AsyncOpenAI`.

**Tech Stack:** `fastmcp>=2.0`, `qdrant-client>=1.9`, `openai>=1.0`, `python-dotenv>=1.0`, `pytest>=8.0`, `pytest-asyncio>=0.24`

**Spec:** `docs/superpowers/specs/2026-03-21-vector-db-mcp-tool-design.md`

---

## File Map

| File | Role |
|---|---|
| `mcp_tools/vector_db/__init__.py` | Empty — makes module importable |
| `mcp_tools/vector_db/server.py` | FastMCP instance, both tools, all helpers |
| `mcp_tools/vector_db/main.py` | Startup env validation + `mcp.run()` |
| `mcp_tools/vector_db/requirements.txt` | Runtime + test dependencies |
| `mcp_tools/vector_db/pytest.ini` | `asyncio_mode = auto` |
| `mcp_tools/vector_db/tests/__init__.py` | Empty — makes tests a package |
| `mcp_tools/vector_db/tests/test_server.py` | 22 unit tests (Qdrant + OpenAI mocked) |
| `mcp_tools/vector_db/tests/test_integration.py` | 1 live test (skipped without env vars) |

---

## Task 1: Project scaffold

**Files:**
- Create: `mcp_tools/vector_db/__init__.py`
- Create: `mcp_tools/vector_db/tests/__init__.py`
- Create: `mcp_tools/vector_db/requirements.txt`
- Create: `mcp_tools/vector_db/pytest.ini`

- [ ] **Step 1: Create directory structure and empty `__init__.py` files**

```bash
mkdir -p mcp_tools/vector_db/tests
touch mcp_tools/vector_db/__init__.py
touch mcp_tools/vector_db/tests/__init__.py
```

- [ ] **Step 2: Write `requirements.txt`**

```
# mcp_tools/vector_db/requirements.txt
fastmcp>=2.0
qdrant-client>=1.9
openai>=1.0
python-dotenv>=1.0

# test dependencies
pytest>=8.0
pytest-asyncio>=0.24
```

- [ ] **Step 3: Write `pytest.ini`**

```ini
# mcp_tools/vector_db/pytest.ini
[pytest]
asyncio_mode = auto
markers =
    integration: marks tests as integration tests (require live QDRANT_URL + OPENAI_API_KEY)
```

- [ ] **Step 4: Install dependencies**

```bash
pip install fastmcp qdrant-client openai python-dotenv pytest pytest-asyncio
```

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/vector_db/
git commit -m "chore: scaffold mcp_tools/vector_db module"
```

---

## Task 2: `_chunk_text` helper with tests

**Files:**
- Create: `mcp_tools/vector_db/server.py`
- Create: `mcp_tools/vector_db/tests/test_server.py`

- [ ] **Step 1: Write the two failing chunking tests**

```python
# mcp_tools/vector_db/tests/test_server.py
import pytest


@pytest.fixture
def mcp_server():
    from mcp_tools.vector_db.server import mcp
    return mcp


def test_chunk_text_splits_into_expected_count():
    """2500-char content with chunk_size=1000, overlap=0 produces 3 chunks."""
    from mcp_tools.vector_db.server import _chunk_text
    chunks = _chunk_text("X" * 2500, chunk_size=1000, overlap=0)
    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
    assert len(chunks[2]) == 500


def test_chunk_text_short_content_returns_single_chunk():
    """Content shorter than chunk_size produces exactly 1 chunk."""
    from mcp_tools.vector_db.server import _chunk_text
    chunks = _chunk_text("Short text", chunk_size=1000, overlap=0)
    assert len(chunks) == 1
    assert chunks[0] == "Short text"


def test_chunk_text_with_overlap_produces_correct_count():
    """2000-char content with chunk_size=1000, overlap=200 produces 3 chunks (sliding window)."""
    from mcp_tools.vector_db.server import _chunk_text
    # Step: 1000 - 200 = 800 per advance
    # chunk 1: [0, 1000), chunk 2: [800, 1800), chunk 3: [1600, 2000)
    chunks = _chunk_text("X" * 2000, chunk_size=1000, overlap=200)
    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
    assert len(chunks[2]) == 400  # remaining 400 chars
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd mcp_tools/vector_db && pytest tests/test_server.py::test_chunk_text_splits_into_expected_count tests/test_server.py::test_chunk_text_short_content_returns_single_chunk tests/test_server.py::test_chunk_text_with_overlap_produces_correct_count -v
```

Expected: `ImportError` or `ModuleNotFoundError` (server.py doesn't exist yet)

- [ ] **Step 3: Create `server.py` with just the FastMCP instance and `_chunk_text`**

```python
# mcp_tools/vector_db/server.py
import asyncio
import json
import os
import uuid

from fastmcp import FastMCP
from mcp.shared.exceptions import McpError, ErrorData
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, INVALID_REQUEST
from openai import AsyncOpenAI, AuthenticationError as OpenAIAuthError
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

mcp = FastMCP("vector-db-tool")

BACKOFF_DELAYS = [1, 2]
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd mcp_tools/vector_db && pytest tests/test_server.py::test_chunk_text_splits_into_expected_count tests/test_server.py::test_chunk_text_short_content_returns_single_chunk -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/vector_db/server.py mcp_tools/vector_db/tests/test_server.py
git commit -m "feat: add _chunk_text helper for character-based document splitting"
```

---

## Task 3: `ingest_document` tool with all ingest tests

**Files:**
- Modify: `mcp_tools/vector_db/server.py` (add `_get_qdrant_client`, `_get_embedding`, `ingest_document`)
- Modify: `mcp_tools/vector_db/tests/test_server.py` (add 14 ingest tests)

### Context: How mocking works here

Unlike `web_search` which uses `respx` for HTTP mocking, here we mock the SDK clients directly:

- `patch("mcp_tools.vector_db.server.AsyncOpenAI")` — patches the constructor; set `return_value` to a mock client
- `patch("mcp_tools.vector_db.server.AsyncQdrantClient")` — same pattern
- `patch("mcp_tools.vector_db.server.asyncio.sleep")` — prevents real delays in retry tests

**Execution order in `ingest_document`:**
1. Input validation (raises before any external call if invalid)
2. `_get_qdrant_client()` — validates `QDRANT_URL`, constructs client
3. `_get_embedding(chunk)` per chunk — validates `OPENAI_API_KEY`, calls OpenAI
4. `qdrant.collection_exists()` + `create_collection()` if needed
5. `qdrant.upsert()` with retry loop

This order means:
- Empty/invalid input tests: no need to mock anything (raises before step 2)
- Missing `QDRANT_URL`: raises at step 2 (no OpenAI mock needed)
- Missing `OPENAI_API_KEY`: raises at step 3 (mock Qdrant constructor to avoid connection attempt)

- [ ] **Step 1: Add the 14 ingest tests to `test_server.py`**

Add all of the following after the existing chunk tests:

```python
import json
import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


# --- Test helpers ---

MOCK_EMBEDDING = [0.1] * 1536


def _mock_openai(embedding=None):
    """Return a mock AsyncOpenAI instance with embeddings.create configured."""
    emb = embedding if embedding is not None else MOCK_EMBEDDING
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=emb)]
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)
    return mock_client


def _mock_qdrant(collection_exists=True):
    """Return a mock AsyncQdrantClient."""
    mock = AsyncMock()
    mock.collection_exists = AsyncMock(return_value=collection_exists)
    mock.create_collection = AsyncMock(return_value=None)
    mock.upsert = AsyncMock(return_value=None)
    mock.search = AsyncMock(return_value=[])
    return mock


# --- Env validation tests ---

@pytest.mark.asyncio
async def test_missing_qdrant_url_raises_on_ingest(mcp_server):
    """ingest_document raises ToolError when QDRANT_URL is not set."""
    with patch.dict(os.environ, {"QDRANT_URL": "", "OPENAI_API_KEY": "test-key"}):
        async with Client(mcp_server) as client:
            with pytest.raises(ToolError):
                await client.call_tool("ingest_document", {
                    "title": "Test", "content": "Some content", "url": "https://example.com"
                })


@pytest.mark.asyncio
async def test_missing_openai_api_key_raises_on_ingest(mcp_server):
    """ingest_document raises ToolError when OPENAI_API_KEY is not set."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": ""}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=_mock_qdrant()):
            async with Client(mcp_server) as client:
                with pytest.raises(ToolError):
                    await client.call_tool("ingest_document", {
                        "title": "Test", "content": "Some content", "url": "https://example.com"
                    })


# --- Happy path tests ---

@pytest.mark.asyncio
async def test_successful_ingest_returns_correct_shape(mcp_server):
    """Successful ingest returns JSON with collection, document_id, chunks_stored, title."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=_mock_qdrant()):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                async with Client(mcp_server) as client:
                    result = await client.call_tool("ingest_document", {
                        "title": "Test Article",
                        "content": "Some content for testing.",
                        "url": "https://example.com/article",
                    })

    data = json.loads(result.content[0].text)
    assert data["collection"] == "documents"
    assert data["title"] == "Test Article"
    assert data["chunks_stored"] == 1
    assert "document_id" in data


@pytest.mark.asyncio
async def test_chunks_stored_matches_expected_count(mcp_server):
    """A 2500-char document with chunk_size=1000, overlap=0 stores 3 chunks."""
    content = "X" * 2500
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=_mock_qdrant()):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                async with Client(mcp_server) as client:
                    result = await client.call_tool("ingest_document", {
                        "title": "T", "content": content, "url": "https://x.com",
                        "chunk_size": 1000, "overlap": 0,
                    })

    data = json.loads(result.content[0].text)
    assert data["chunks_stored"] == 3


@pytest.mark.asyncio
async def test_ingest_creates_collection_when_missing(mcp_server):
    """ingest_document calls create_collection when the collection doesn't exist."""
    mock_qdrant = _mock_qdrant(collection_exists=False)
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                async with Client(mcp_server) as client:
                    await client.call_tool("ingest_document", {
                        "title": "T", "content": "Content", "url": "https://x.com",
                    })

    mock_qdrant.create_collection.assert_called_once()


# --- Input validation tests (no external calls) ---

@pytest.mark.asyncio
async def test_empty_content_raises_without_external_call(mcp_server):
    """Empty content raises ToolError before any external call."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient") as mock_qdrant_cls:
            with patch("mcp_tools.vector_db.server.AsyncOpenAI") as mock_openai_cls:
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("ingest_document", {
                            "title": "T", "content": "", "url": "https://x.com"
                        })

    mock_qdrant_cls.assert_not_called()
    mock_openai_cls.assert_not_called()


@pytest.mark.asyncio
async def test_chunk_size_zero_raises_without_external_call(mcp_server):
    """chunk_size=0 raises ToolError before any external call."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient") as mock_qdrant_cls:
            with patch("mcp_tools.vector_db.server.AsyncOpenAI") as mock_openai_cls:
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("ingest_document", {
                            "title": "T", "content": "Content", "url": "https://x.com",
                            "chunk_size": 0,
                        })

    mock_qdrant_cls.assert_not_called()
    mock_openai_cls.assert_not_called()


@pytest.mark.asyncio
async def test_chunk_size_5001_raises_without_external_call(mcp_server):
    """chunk_size=5001 raises ToolError before any external call."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient") as mock_qdrant_cls:
            with patch("mcp_tools.vector_db.server.AsyncOpenAI") as mock_openai_cls:
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("ingest_document", {
                            "title": "T", "content": "Content", "url": "https://x.com",
                            "chunk_size": 5001,
                        })

    mock_qdrant_cls.assert_not_called()
    mock_openai_cls.assert_not_called()


@pytest.mark.asyncio
async def test_overlap_equals_chunk_size_raises_without_external_call(mcp_server):
    """overlap >= chunk_size raises ToolError before any external call."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient") as mock_qdrant_cls:
            with patch("mcp_tools.vector_db.server.AsyncOpenAI") as mock_openai_cls:
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("ingest_document", {
                            "title": "T", "content": "Content", "url": "https://x.com",
                            "chunk_size": 500, "overlap": 500,
                        })

    mock_qdrant_cls.assert_not_called()
    mock_openai_cls.assert_not_called()


# --- Retry and error handling tests ---

@pytest.mark.asyncio
async def test_openai_401_raises_immediately_on_ingest(mcp_server):
    """OpenAI 401 raises ToolError immediately — no retry."""
    import httpx
    from openai import AuthenticationError

    mock_req = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    auth_error = AuthenticationError(
        "invalid api key",
        response=httpx.Response(401, request=mock_req),
        body={},
    )

    mock_qdrant = _mock_qdrant()
    mock_openai_client = AsyncMock()
    mock_openai_client.embeddings.create = AsyncMock(side_effect=auth_error)

    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "bad-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=mock_openai_client):
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("ingest_document", {
                            "title": "T", "content": "Content", "url": "https://x.com"
                        })

    assert mock_openai_client.embeddings.create.call_count == 1


@pytest.mark.asyncio
async def test_openai_429_retries_then_raises_on_ingest(mcp_server):
    """OpenAI errors (non-401) are retried; raises ToolError after 3 failures."""
    mock_qdrant = _mock_qdrant()
    mock_openai_client = AsyncMock()
    mock_openai_client.embeddings.create = AsyncMock(side_effect=Exception("rate limit"))

    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.asyncio.sleep"):
            with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
                with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=mock_openai_client):
                    async with Client(mcp_server) as client:
                        with pytest.raises(ToolError):
                            await client.call_tool("ingest_document", {
                                "title": "T", "content": "Content", "url": "https://x.com"
                            })

    assert mock_openai_client.embeddings.create.call_count == 3


@pytest.mark.asyncio
async def test_qdrant_upsert_retries_then_raises(mcp_server):
    """Qdrant upsert failures are retried; raises ToolError after 3 attempts."""
    mock_qdrant = _mock_qdrant(collection_exists=True)
    mock_qdrant.upsert = AsyncMock(side_effect=Exception("connection refused"))

    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.asyncio.sleep"):
            with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
                with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                    async with Client(mcp_server) as client:
                        with pytest.raises(ToolError):
                            await client.call_tool("ingest_document", {
                                "title": "T", "content": "Content", "url": "https://x.com"
                            })

    assert mock_qdrant.upsert.call_count == 3


@pytest.mark.asyncio
async def test_qdrant_upsert_recovers_on_third_attempt(mcp_server):
    """Qdrant upsert fails twice then succeeds on the third attempt."""
    mock_qdrant = _mock_qdrant(collection_exists=True)
    mock_qdrant.upsert = AsyncMock(side_effect=[
        Exception("timeout"),
        Exception("timeout"),
        None,  # success
    ])

    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.asyncio.sleep"):
            with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
                with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                    async with Client(mcp_server) as client:
                        result = await client.call_tool("ingest_document", {
                            "title": "T", "content": "Content", "url": "https://x.com"
                        })

    assert mock_qdrant.upsert.call_count == 3
    data = json.loads(result.content[0].text)
    assert "document_id" in data
```

- [ ] **Step 2: Run tests to verify all 14 new ingest tests fail**

```bash
cd mcp_tools/vector_db && pytest tests/test_server.py -k "ingest or missing_qdrant or missing_openai" -v
```

Expected: All fail (tools not implemented yet)

- [ ] **Step 3: Add helpers and `ingest_document` to `server.py`**

Add after `_chunk_text`:

```python
def _get_qdrant_client() -> AsyncQdrantClient:
    url = os.environ.get("QDRANT_URL", "")
    if not url:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="QDRANT_URL environment variable is not set"))
    return AsyncQdrantClient(url=url)


async def _get_embedding(text: str) -> list[float]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="OPENAI_API_KEY environment variable is not set"))
    client = AsyncOpenAI(api_key=api_key)
    last_error = "unknown error"
    for attempt in range(3):
        if attempt > 0:
            await asyncio.sleep(BACKOFF_DELAYS[attempt - 1])
        try:
            response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text)
            return response.data[0].embedding
        except OpenAIAuthError:
            raise McpError(ErrorData(code=INVALID_REQUEST, message="OpenAI authentication failed (401)"))
        except Exception as e:
            last_error = str(e)
            continue
    raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"OpenAI embedding failed after 3 attempts: {last_error}"))


@mcp.tool
async def ingest_document(
    title: str,
    content: str,
    url: str,
    collection: str = "documents",
    chunk_size: int = 1000,
    overlap: int = 200,
) -> str:
    """Chunk a document and ingest it into the vector database."""
    if not title or not title.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="title must not be empty"))
    if not content or not content.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="content must not be empty"))
    if not url or not url.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="url must not be empty"))
    if not collection or not collection.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="collection must not be empty"))
    if not 1 <= chunk_size <= 5000:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="chunk_size must be between 1 and 5000"))
    if not 0 <= overlap <= 500:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="overlap must be between 0 and 500"))
    if overlap >= chunk_size:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="overlap must be less than chunk_size"))

    qdrant = _get_qdrant_client()
    document_id = str(uuid.uuid4())
    chunks = _chunk_text(content, chunk_size, overlap)

    embeddings = []
    for chunk in chunks:
        embeddings.append(await _get_embedding(chunk))

    if not await qdrant.collection_exists(collection):
        await qdrant.create_collection(
            collection,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embeddings[i],
            payload={
                "document_id": document_id,
                "title": title,
                "url": url,
                "content": chunks[i],
                "chunk_index": i,
            },
        )
        for i in range(len(chunks))
    ]

    last_error = "unknown error"
    for attempt in range(3):
        if attempt > 0:
            await asyncio.sleep(BACKOFF_DELAYS[attempt - 1])
        try:
            await qdrant.upsert(collection_name=collection, points=points)
            break
        except Exception as e:
            last_error = str(e)
            continue
    else:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Qdrant upsert failed after 3 attempts: {last_error}"))

    return json.dumps({
        "collection": collection,
        "document_id": document_id,
        "chunks_stored": len(chunks),
        "title": title,
    })
```

- [ ] **Step 4: Run all tests to verify all pass**

```bash
cd mcp_tools/vector_db && pytest tests/test_server.py -v
```

Expected: All tests pass (chunking + ingest tests)

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/vector_db/server.py mcp_tools/vector_db/tests/test_server.py
git commit -m "feat: add ingest_document tool with chunking, embedding, and retry logic"
```

---

## Task 4: `search_documents` tool with all search tests

**Files:**
- Modify: `mcp_tools/vector_db/server.py` (add `search_documents`)
- Modify: `mcp_tools/vector_db/tests/test_server.py` (add 6 search tests)

**Execution order in `search_documents`:**
1. Input validation (raises before any external call)
2. `_get_qdrant_client()` — validates `QDRANT_URL` (cheap check first)
3. `qdrant.collection_exists()` — raises `INVALID_REQUEST` immediately if missing (no paid API call wasted)
4. `_get_embedding(query)` — validates `OPENAI_API_KEY`, calls OpenAI (only reached if collection exists)
5. `qdrant.search()` — retry loop

- [ ] **Step 1: Add the 6 search tests to `test_server.py`**

```python
# --- search_documents tests ---

@pytest.mark.asyncio
async def test_successful_search_returns_correct_shape(mcp_server):
    """Successful search returns JSON with query, collection, and results list."""
    mock_hit = MagicMock()
    mock_hit.payload = {"title": "Test Doc", "url": "https://example.com", "content": "Relevant text"}
    mock_hit.score = 0.92

    mock_qdrant = _mock_qdrant(collection_exists=True)
    mock_qdrant.search = AsyncMock(return_value=[mock_hit])

    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                async with Client(mcp_server) as client:
                    result = await client.call_tool("search_documents", {"query": "test query"})

    data = json.loads(result.content[0].text)
    assert data["query"] == "test query"
    assert data["collection"] == "documents"
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Test Doc"
    assert data["results"][0]["url"] == "https://example.com"
    assert isinstance(data["results"][0]["score"], float)


@pytest.mark.asyncio
async def test_empty_query_raises_without_external_call(mcp_server):
    """Empty query raises ToolError before any external call."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient") as mock_qdrant_cls:
            with patch("mcp_tools.vector_db.server.AsyncOpenAI") as mock_openai_cls:
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("search_documents", {"query": ""})

    mock_qdrant_cls.assert_not_called()
    mock_openai_cls.assert_not_called()


@pytest.mark.asyncio
async def test_num_results_zero_raises_without_external_call(mcp_server):
    """num_results=0 raises ToolError before any external call."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient") as mock_qdrant_cls:
            with patch("mcp_tools.vector_db.server.AsyncOpenAI") as mock_openai_cls:
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("search_documents", {
                            "query": "test", "num_results": 0
                        })

    mock_qdrant_cls.assert_not_called()
    mock_openai_cls.assert_not_called()


@pytest.mark.asyncio
async def test_num_results_21_raises_without_external_call(mcp_server):
    """num_results=21 raises ToolError before any external call."""
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient") as mock_qdrant_cls:
            with patch("mcp_tools.vector_db.server.AsyncOpenAI") as mock_openai_cls:
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("search_documents", {
                            "query": "test", "num_results": 21
                        })

    mock_qdrant_cls.assert_not_called()
    mock_openai_cls.assert_not_called()


@pytest.mark.asyncio
async def test_search_missing_collection_raises_immediately(mcp_server):
    """search_documents raises ToolError immediately if collection doesn't exist — no Qdrant search call."""
    mock_qdrant = _mock_qdrant(collection_exists=False)

    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                async with Client(mcp_server) as client:
                    with pytest.raises(ToolError):
                        await client.call_tool("search_documents", {"query": "test"})

    mock_qdrant.search.assert_not_called()


@pytest.mark.asyncio
async def test_collection_param_routes_to_correct_collection(mcp_server):
    """The collection parameter is passed through to Qdrant search."""
    mock_qdrant = _mock_qdrant(collection_exists=True)

    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                async with Client(mcp_server) as client:
                    await client.call_tool("search_documents", {
                        "query": "test", "collection": "my_research"
                    })

    mock_qdrant.search.assert_called_once()
    assert mock_qdrant.search.call_args.kwargs["collection_name"] == "my_research"
```

- [ ] **Step 2: Run new search tests to verify they fail**

```bash
cd mcp_tools/vector_db && pytest tests/test_server.py -k "search" -v
```

Expected: All 6 fail (`search_documents` not implemented yet)

- [ ] **Step 3: Add `search_documents` to `server.py`**

Append after `ingest_document`:

```python
@mcp.tool
async def search_documents(
    query: str,
    collection: str = "documents",
    num_results: int = 5,
) -> str:
    """Search the vector database for documents semantically similar to a query."""
    if not query or not query.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="query must not be empty"))
    if not collection or not collection.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="collection must not be empty"))
    if not 1 <= num_results <= 20:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="num_results must be between 1 and 20"))

    qdrant = _get_qdrant_client()

    if not await qdrant.collection_exists(collection):
        raise McpError(ErrorData(code=INVALID_REQUEST, message=f"Collection '{collection}' does not exist"))

    query_vector = await _get_embedding(query)

    last_error = "unknown error"
    for attempt in range(3):
        if attempt > 0:
            await asyncio.sleep(BACKOFF_DELAYS[attempt - 1])
        try:
            results = await qdrant.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=num_results,
            )
            break
        except Exception as e:
            last_error = str(e)
            continue
    else:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Qdrant search failed after 3 attempts: {last_error}"))

    return json.dumps({
        "query": query,
        "collection": collection,
        "results": [
            {
                "title": r.payload.get("title", ""),
                "url": r.payload.get("url", ""),
                "content": r.payload.get("content", ""),
                "score": float(r.score),
            }
            for r in results
        ],
    })
```

- [ ] **Step 4: Run all tests**

```bash
cd mcp_tools/vector_db && pytest tests/test_server.py -v
```

Expected: All 22 tests pass

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/vector_db/server.py mcp_tools/vector_db/tests/test_server.py
git commit -m "feat: add search_documents tool with embedding, collection check, and retry logic"
```

---

## Task 5: `main.py`, integration test, and codemaps update

**Files:**
- Create: `mcp_tools/vector_db/main.py`
- Create: `mcp_tools/vector_db/tests/test_integration.py`
- Modify: `docs/CODEMAPS/architecture.md`
- Modify: `docs/CODEMAPS/mcp_tools.md`
- Modify: `docs/CODEMAPS/dependencies.md`

- [ ] **Step 1: Write `main.py`**

```python
# mcp_tools/vector_db/main.py
import os
import sys

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

- [ ] **Step 2: Write `test_integration.py`**

```python
# mcp_tools/vector_db/tests/test_integration.py
import json
import os

import pytest
from fastmcp import Client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ingest_and_search_live():
    """Ingest one document and search for it against a live Qdrant + OpenAI."""
    qdrant_url = os.environ.get("QDRANT_URL")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not qdrant_url or not openai_key:
        pytest.skip("QDRANT_URL and OPENAI_API_KEY required for integration test")

    from mcp_tools.vector_db.server import mcp

    async with Client(mcp) as client:
        # Ingest
        ingest_result = await client.call_tool("ingest_document", {
            "title": "Integration Test Document",
            "content": "Qdrant is a vector database for storing and searching embeddings.",
            "url": "https://qdrant.tech",
            "collection": "integration_test",
        })
        ingest_data = json.loads(ingest_result.content[0].text)
        assert ingest_data["chunks_stored"] >= 1

        # Search
        search_result = await client.call_tool("search_documents", {
            "query": "vector database embeddings",
            "collection": "integration_test",
            "num_results": 1,
        })
        search_data = json.loads(search_result.content[0].text)
        assert len(search_data["results"]) >= 1
        assert search_data["results"][0]["url"] == "https://qdrant.tech"
```

- [ ] **Step 3: Run the full unit test suite one final time**

```bash
cd mcp_tools/vector_db && pytest tests/test_server.py -v
```

Expected: All 22 tests pass

- [ ] **Step 4: Update `docs/CODEMAPS/architecture.md`**

Change the `vector_db` row from `⬜ Planned` to `✅ Built`:

```markdown
| `mcp_tools/vector_db` | ✅ Built | 9002 |
```

- [ ] **Step 5: Update `docs/CODEMAPS/mcp_tools.md`**

Replace the `vector_db ⬜` stub with:

```markdown
## vector_db ✅ (port 9002)

```
main.py  →  load_dotenv() → validate QDRANT_URL + OPENAI_API_KEY → mcp.run(transport="http", port=9002)
server.py →  FastMCP("vector-db-tool")
              ├── _chunk_text(text, chunk_size, overlap) → list[str]
              ├── _get_qdrant_client() → AsyncQdrantClient  (validates QDRANT_URL)
              ├── _get_embedding(text) → list[float]  (text-embedding-3-small, retries)
              ├── ingest_document(title, content, url, collection, chunk_size, overlap) → str (JSON)
              │     ├── validate inputs, chunk, embed per chunk
              │     ├── create_collection if not exists (VectorParams size=1536, cosine)
              │     └── upsert PointStructs with retry [1s, 2s]
              └── search_documents(query, collection, num_results) → str (JSON)
                    ├── embed query, check collection exists
                    └── search with retry [1s, 2s]
```

**Response shapes:**
```json
// ingest_document
{"collection": "...", "document_id": "uuid", "chunks_stored": 4, "title": "..."}
// search_documents
{"query": "...", "collection": "...", "results": [{"title","url","content","score"}]}
```

**Key files:**
- `mcp_tools/vector_db/server.py` — tool logic, helpers, retry (~160 lines)
- `mcp_tools/vector_db/main.py` — entrypoint, dual env validation (~15 lines)
- `mcp_tools/vector_db/tests/test_server.py` — 20 unit tests
- `mcp_tools/vector_db/tests/test_integration.py` — 1 live test

**Env vars:** `QDRANT_URL` (required), `OPENAI_API_KEY` (required)
```

- [ ] **Step 6: Update `docs/CODEMAPS/dependencies.md`**

Add `qdrant-client` and `openai` to the installed libraries section under `vector_db`.

- [ ] **Step 7: Commit everything**

```bash
git add mcp_tools/vector_db/ docs/CODEMAPS/
git commit -m "feat: add vector_db MCP tool — Qdrant-backed ingest and semantic search"
```
