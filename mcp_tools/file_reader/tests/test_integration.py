# mcp_tools/file_reader/tests/test_integration.py
import json
import os
import pytest
from fastmcp import Client

pytestmark = pytest.mark.integration

FIXTURE_PDF = os.path.join(os.path.dirname(__file__), "fixtures", "sample.pdf")


@pytest.fixture
def mcp_server():
    from mcp_tools.file_reader.server import mcp
    return mcp


async def test_read_fixture_pdf(mcp_server):
    """Read the bundled sample.pdf fixture — always runs (no env vars required)."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": FIXTURE_PDF})

    data = json.loads(result.content[0].text)
    assert data["file_type"] == "pdf"
    assert isinstance(data["text"], str)
    assert len(data["text"]) > 0
    meta = data["metadata"]
    assert isinstance(meta["page_count"], int)
    assert meta["page_count"] > 0
    assert meta["title"] == "Sample Test PDF"
