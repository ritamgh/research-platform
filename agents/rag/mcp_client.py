"""MCP clients for vector_db (port 9002) and file_reader (port 9003) tool servers."""
import os
from fastmcp import Client

VECTOR_DB_MCP_URL = os.environ.get("VECTOR_DB_MCP_URL", "http://localhost:9002/mcp")
FILE_READER_MCP_URL = os.environ.get("FILE_READER_MCP_URL", "http://localhost:9003/mcp")


async def search_documents(query: str, top_k: int = 5) -> str:
    """Search the vector DB for documents relevant to the query."""
    async with Client(VECTOR_DB_MCP_URL) as client:
        result = await client.call_tool(
            "search_documents",
            {"query": query, "num_results": top_k},
        )
        return result.content[0].text


async def read_file(source: str) -> str:
    """Read and parse a file (local path or URL) via the file_reader MCP."""
    async with Client(FILE_READER_MCP_URL) as client:
        result = await client.call_tool(
            "read_file",
            {"source": source},
        )
        return result.content[0].text
