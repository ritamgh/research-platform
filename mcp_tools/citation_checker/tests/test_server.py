# mcp_tools/citation_checker/tests/test_server.py
import json
import pytest
import httpx
import respx
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


async def test_credibility_whitespace_url_raises(mcp_server):
    """Whitespace-only url raises ToolError (caught by .strip() check)."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_credibility", {"url": "   "})


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


# ---------------------------------------------------------------------------
# check_reachability — input validation
# ---------------------------------------------------------------------------

async def test_reachability_empty_url_raises(mcp_server):
    """Empty url raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_reachability", {"url": ""})


async def test_reachability_whitespace_url_raises(mcp_server):
    """Whitespace-only url raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_reachability", {"url": "   "})


async def test_reachability_non_http_scheme_raises(mcp_server):
    """Non-http/https scheme (e.g. ftp://) raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_reachability", {"url": "ftp://example.com"})


async def test_reachability_empty_hostname_raises(mcp_server):
    """URL with empty hostname after scheme (e.g. https:///path) raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("check_reachability", {"url": "https:///path"})


# ---------------------------------------------------------------------------
# check_reachability — happy paths
# ---------------------------------------------------------------------------

async def test_reachability_happy_path(mcp_server):
    """Successful HEAD returns reachable=true with status_code, latency_ms, final_url."""
    with respx.mock:
        respx.head("https://arxiv.org/").mock(return_value=httpx.Response(200))
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://arxiv.org/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert data["status_code"] == 200
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0
    assert data["final_url"] == "https://arxiv.org/"


async def test_reachability_404_is_reachable(mcp_server):
    """404 response counts as reachable=true (server responded)."""
    with respx.mock:
        respx.head("https://example.com/missing").mock(return_value=httpx.Response(404))
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://example.com/missing"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert data["status_code"] == 404


async def test_reachability_redirect_final_url(mcp_server):
    """Redirects are followed; final_url reflects the resolved URL."""
    with respx.mock:
        respx.head("http://old.example.com/").mock(
            return_value=httpx.Response(301, headers={"location": "https://new.example.com/"})
        )
        respx.head("https://new.example.com/").mock(return_value=httpx.Response(200))
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "http://old.example.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is True
    assert data["url"] == "http://old.example.com/"
    assert data["final_url"] == "https://new.example.com/"


# ---------------------------------------------------------------------------
# check_reachability — network failures → reachable=false
# ---------------------------------------------------------------------------

async def test_reachability_timeout_returns_unreachable(mcp_server):
    """Timeout returns reachable=false with all null fields."""
    with respx.mock:
        respx.head("https://slow.example.com/").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://slow.example.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is False
    assert data["status_code"] is None
    assert data["latency_ms"] is None
    assert data["final_url"] is None


async def test_reachability_connect_error_returns_unreachable(mcp_server):
    """ConnectError (DNS failure, refused) returns reachable=false."""
    with respx.mock:
        respx.head("https://unreachable.example.com/").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://unreachable.example.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is False
    assert data["status_code"] is None


async def test_reachability_too_many_redirects_returns_unreachable(mcp_server):
    """TooManyRedirects (httpx.HTTPError subclass) returns reachable=false."""
    req = httpx.Request("HEAD", "https://redirect-loop.com/")
    with respx.mock:
        respx.head("https://redirect-loop.com/").mock(
            side_effect=httpx.TooManyRedirects("too many redirects", request=req)
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool("check_reachability", {"url": "https://redirect-loop.com/"})
    data = json.loads(result.content[0].text)
    assert data["reachable"] is False
    assert data["status_code"] is None
