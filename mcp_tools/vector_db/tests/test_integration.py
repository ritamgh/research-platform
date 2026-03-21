# mcp_tools/vector_db/tests/test_integration.py
import os
import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.integration


@pytest.fixture
def mcp_server():
    from mcp_tools.vector_db.server import mcp
    return mcp


@pytest.mark.skipif(
    not os.environ.get("QDRANT_URL") or not os.environ.get("OPENAI_API_KEY"),
    reason="QDRANT_URL and OPENAI_API_KEY required for integration tests",
)
@pytest.mark.asyncio
async def test_ingest_and_search_roundtrip(mcp_server):
    """Ingest a document and verify it can be searched."""
    async with Client(mcp_server) as client:
        # Ingest
        ingest_result = await client.call_tool("ingest_document", {
            "title": "Integration Test Document",
            "content": "This is a test document about artificial intelligence and machine learning.",
            "url": "https://example.com/test",
            "collection": "integration_test",
        })
        ingest_data = json.loads(ingest_result.content[0].text)
        assert ingest_data["chunks_stored"] >= 1
        assert ingest_data["collection"] == "integration_test"

        # Search
        search_result = await client.call_tool("search_documents", {
            "query": "artificial intelligence",
            "collection": "integration_test",
            "num_results": 1,
        })
        search_data = json.loads(search_result.content[0].text)
        assert len(search_data["results"]) >= 1
        assert search_data["results"][0]["title"] == "Integration Test Document"
