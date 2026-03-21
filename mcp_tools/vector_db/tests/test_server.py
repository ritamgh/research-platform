# mcp_tools/vector_db/tests/test_server.py
import json
import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


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


@pytest.mark.asyncio
async def test_ingest_collection_param_routes_to_correct_collection(mcp_server):
    """The collection parameter is used for collection_exists and upsert calls."""
    mock_qdrant = _mock_qdrant(collection_exists=True)
    with patch.dict(os.environ, {"QDRANT_URL": "http://localhost:6333", "OPENAI_API_KEY": "test-key"}):
        with patch("mcp_tools.vector_db.server.AsyncQdrantClient", return_value=mock_qdrant):
            with patch("mcp_tools.vector_db.server.AsyncOpenAI", return_value=_mock_openai()):
                async with Client(mcp_server) as client:
                    await client.call_tool("ingest_document", {
                        "title": "T", "content": "Content", "url": "https://x.com",
                        "collection": "my_research",
                    })

    mock_qdrant.collection_exists.assert_called_once_with("my_research")
    mock_qdrant.upsert.assert_called_once()
    assert mock_qdrant.upsert.call_args.kwargs["collection_name"] == "my_research"
