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
