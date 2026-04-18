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
    if chunk_size <= 0 or overlap >= chunk_size:
        raise ValueError(f"Invalid chunking params: chunk_size={chunk_size}, overlap={overlap}")
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


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
            response = await qdrant.query_points(
                collection_name=collection,
                query=query_vector,
                limit=num_results,
            )
            results = response.points
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


@mcp.tool
async def list_documents(collection: str = "documents") -> str:
    """List all unique documents ingested into a collection."""
    if not collection or not collection.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="collection must not be empty"))

    qdrant = _get_qdrant_client()

    if not await qdrant.collection_exists(collection):
        return json.dumps({"collection": collection, "documents": []})

    seen: dict[str, dict] = {}
    offset = None
    while True:
        response, next_offset = await qdrant.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in response:
            doc_id = point.payload.get("document_id", "")
            if doc_id and doc_id not in seen:
                seen[doc_id] = {
                    "document_id": doc_id,
                    "title": point.payload.get("title", ""),
                    "url": point.payload.get("url", ""),
                    "chunk_count": 0,
                }
            if doc_id:
                seen[doc_id]["chunk_count"] += 1
        if next_offset is None:
            break
        offset = next_offset

    return json.dumps({
        "collection": collection,
        "documents": list(seen.values()),
    })
