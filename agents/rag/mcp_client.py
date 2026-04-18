"""MCP clients for vector_db (port 9002) and file_reader (port 9003) tool servers."""
import os
from fastmcp import Client

VECTOR_DB_MCP_URL = os.environ.get("VECTOR_DB_MCP_URL", "http://localhost:9002/mcp")
FILE_READER_MCP_URL = os.environ.get("FILE_READER_MCP_URL", "http://localhost:9003/mcp")

# Module-level clients — avoids creating a new HTTP/SSE connection on every call.
_vector_db_client: Client | None = None
_file_reader_client: Client | None = None


def _get_vector_db_client() -> Client:
    global _vector_db_client
    if _vector_db_client is None:
        _vector_db_client = Client(VECTOR_DB_MCP_URL)
    return _vector_db_client


def _get_file_reader_client() -> Client:
    global _file_reader_client
    if _file_reader_client is None:
        _file_reader_client = Client(FILE_READER_MCP_URL)
    return _file_reader_client


async def search_documents(query: str, top_k: int = 5) -> str:
    """Search the vector DB for documents relevant to the query."""
    async with _get_vector_db_client() as client:
        result = await client.call_tool(
            "search_documents",
            {"query": query, "num_results": top_k},
        )
        return result.content[0].text


async def read_file(source: str) -> str:
    """Read and parse a file (local path or URL) via the file_reader MCP."""
    async with _get_file_reader_client() as client:
        result = await client.call_tool(
            "read_file",
            {"source": source},
        )
        return result.content[0].text
