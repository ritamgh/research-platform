# mcp_tools/citation_checker/tests/test_integration.py
import json
import socket
import pytest
from fastmcp import Client

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def skip_if_no_network():
    """Auto-skip this test module if the network is unavailable."""
    try:
        socket.create_connection(("arxiv.org", 443), timeout=3)
    except OSError:
        pytest.skip("Network unavailable")


@pytest.fixture
def mcp_server():
    from mcp_tools.citation_checker.server import mcp
    return mcp


async def test_check_reachability_live(mcp_server):
    """Live HEAD request to arxiv.org — skipped automatically if offline."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_reachability", {"url": "https://arxiv.org/"})

    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert isinstance(data["status_code"], int)
    assert data["status_code"] > 0
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0
    assert data["final_url"] is not None
