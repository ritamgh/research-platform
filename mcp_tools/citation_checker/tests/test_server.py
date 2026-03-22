# mcp_tools/citation_checker/tests/test_server.py
import json
import pytest
import respx
import httpx
from fastmcp import Client
from fastmcp.exceptions import ToolError


@pytest.fixture
def mcp_server():
    from mcp_tools.citation_checker.server import mcp
    return mcp


# ---------------------------------------------------------------------------
# check_credibility — input validation
# ---------------------------------------------------------------------------

async def test_credibility_empty_url_raises(mcp_server):
    """Empty url raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_credibility", {"url": ""})


async def test_credibility_schemeless_url_raises(mcp_server):
    """Schemeless string (no ://) produces empty hostname and raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_credibility", {"url": "arxiv.org/abs/123"})


async def test_credibility_unparseable_url_raises(mcp_server):
    """String with no parseable hostname raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_credibility", {"url": "not-a-url"})


# ---------------------------------------------------------------------------
# check_credibility — scheme handling
# ---------------------------------------------------------------------------

async def test_credibility_ftp_scheme_accepted(mcp_server):
    """Non-http/https scheme is accepted; scoring is domain-based only."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "ftp://arxiv.org/paper"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["label"] == "high"


# ---------------------------------------------------------------------------
# check_credibility — tier 1: research domains
# ---------------------------------------------------------------------------

async def test_credibility_research_domain(mcp_server):
    """Known research domain (arxiv.org) scores 0.9 / high / 'Known research publisher'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://arxiv.org/abs/2301.00001"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["label"] == "high"
    assert data["reason"] == "Known research publisher"


# ---------------------------------------------------------------------------
# check_credibility — tier 2: credible news/health domains
# ---------------------------------------------------------------------------

async def test_credibility_news_domain(mcp_server):
    """Known news domain (reuters.com) scores 0.9 / high / 'Known credible news/health source'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://reuters.com/article/x"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["label"] == "high"
    assert data["reason"] == "Known credible news/health source"


# ---------------------------------------------------------------------------
# check_credibility — tier 3: blog hosts
# ---------------------------------------------------------------------------

async def test_credibility_blog_host(mcp_server):
    """Free blog host (wordpress.com) scores 0.2 / low / 'Free blog host'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://wordpress.com/post/123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.2
    assert data["label"] == "low"
    assert data["reason"] == "Free blog host"


# ---------------------------------------------------------------------------
# check_credibility — tier 4: URL shorteners
# ---------------------------------------------------------------------------

async def test_credibility_url_shortener(mcp_server):
    """URL shortener (bit.ly) scores 0.2 / low / 'URL shortener'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://bit.ly/abc123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.2
    assert data["label"] == "low"
    assert data["reason"] == "URL shortener"


# ---------------------------------------------------------------------------
# check_credibility — tier 5: low-credibility TLDs
# ---------------------------------------------------------------------------

async def test_credibility_low_tld(mcp_server):
    """Low-credibility TLD (.xyz) scores 0.1 / low."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://example.xyz/page"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.1
    assert data["label"] == "low"


# ---------------------------------------------------------------------------
# check_credibility — tier 6: TLD fallback
# ---------------------------------------------------------------------------

async def test_credibility_edu_tld(mcp_server):
    """.edu TLD fallback scores 0.85 / high."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://mit.edu/research/paper"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.85
    assert data["label"] == "high"


async def test_credibility_gov_tld(mcp_server):
    """.gov TLD fallback scores 0.85 / high."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://nasa.gov/report"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.85
    assert data["label"] == "high"


async def test_credibility_org_tld(mcp_server):
    """.org TLD fallback scores 0.6 / medium."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://unknown-org.org/page"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.6
    assert data["label"] == "medium"


async def test_credibility_com_tld(mcp_server):
    """.com TLD fallback scores 0.5 / medium."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://unknown-site.com/page"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.5
    assert data["label"] == "medium"


async def test_credibility_unknown_tld(mcp_server):
    """Unknown TLD fallback scores 0.4 / medium."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://example.museum/exhibit"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.4
    assert data["label"] == "medium"


# ---------------------------------------------------------------------------
# check_credibility — hostname parsing edge cases
# ---------------------------------------------------------------------------

async def test_credibility_www_stripped(mcp_server):
    """www. prefix is stripped before domain lookup."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://www.arxiv.org/abs/123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
    assert data["reason"] == "Known research publisher"


async def test_credibility_port_and_path_ignored(mcp_server):
    """Port and path are ignored; only hostname is used for scoring."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("check_credibility", {"url": "https://arxiv.org:8080/abs/123"})
    data = json.loads(result.content[0].text)
    assert data["score"] == 0.9
