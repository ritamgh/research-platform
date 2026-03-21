# mcp_tools/file_reader/tests/test_server.py
import json
import os
import pytest
import respx
import httpx
import fitz
from unittest.mock import patch
from fastmcp import Client
from fastmcp.exceptions import ToolError


@pytest.fixture
def mcp_server():
    from mcp_tools.file_reader.server import mcp
    return mcp


# ---------------------------------------------------------------------------
# Input validation (no I/O needed — errors raised before any external call)
# ---------------------------------------------------------------------------

async def test_empty_source_raises(mcp_server):
    """Empty source raises ToolError before any I/O."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {"source": ""})


async def test_http_url_raises(mcp_server):
    """http:// (non-https) URL raises ToolError with helpful message."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError, match="https"):
            await client.call_tool("read_file", {"source": "http://example.com/file.pdf"})


async def test_start_page_zero_raises(mcp_server, tmp_path):
    """start_page=0 raises ToolError before any I/O."""
    fake = tmp_path / "file.pdf"
    fake.write_bytes(b"x")
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {"source": str(fake), "start_page": 0})


async def test_end_page_less_than_start_page_raises(mcp_server, tmp_path):
    """end_page < start_page raises ToolError before any I/O."""
    fake = tmp_path / "file.pdf"
    fake.write_bytes(b"x")
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {
                "source": str(fake),
                "start_page": 5,
                "end_page": 3,
            })


async def test_unsupported_extension_raises(mcp_server, tmp_path):
    """Unsupported extension (.docx) raises ToolError."""
    fake = tmp_path / "file.docx"
    fake.write_bytes(b"x")
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {"source": str(fake)})


async def test_extensionless_local_path_raises(mcp_server, tmp_path):
    """Local path with no extension raises ToolError."""
    fake = tmp_path / "myfile"
    fake.write_bytes(b"hello")
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {"source": str(fake)})


# ---------------------------------------------------------------------------
# Local file I/O errors
# ---------------------------------------------------------------------------

async def test_local_file_not_found_raises(mcp_server):
    """Non-existent local path raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {"source": "/nonexistent/path/file.pdf"})


# ---------------------------------------------------------------------------
# Local PDF — happy path + metadata + page ranges
# ---------------------------------------------------------------------------

FIXTURE_PDF = os.path.join(os.path.dirname(__file__), "fixtures", "sample.pdf")


async def test_local_pdf_happy_path_returns_correct_shape(mcp_server):
    """Local PDF returns correct JSON shape with all expected fields."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": FIXTURE_PDF})

    data = json.loads(result.content[0].text)
    assert data["source"] == FIXTURE_PDF
    assert data["file_type"] == "pdf"
    assert isinstance(data["text"], str)
    assert len(data["text"]) > 0
    assert "metadata" in data


async def test_local_pdf_text_extraction(mcp_server):
    """Extracted text contains content from the fixture PDF."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": FIXTURE_PDF})

    data = json.loads(result.content[0].text)
    assert "sample PDF" in data["text"].lower() or "testing" in data["text"].lower()


async def test_local_pdf_metadata_fields(mcp_server):
    """PDF metadata includes title, author, page_count."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": FIXTURE_PDF})

    meta = json.loads(result.content[0].text)["metadata"]
    assert meta["title"] == "Sample Test PDF"
    assert meta["author"] == "Test Author"
    assert meta["page_count"] == 2


async def test_empty_metadata_fields_returned_as_null(mcp_server, tmp_path):
    """PDF with no embedded metadata returns null for title/author, not empty string."""
    doc = fitz.open()
    doc.insert_page(-1, text="Content without metadata.")
    pdf_path = tmp_path / "no_meta.pdf"
    doc.save(str(pdf_path))
    doc.close()

    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": str(pdf_path)})

    meta = json.loads(result.content[0].text)["metadata"]
    assert meta["title"] is None
    assert meta["author"] is None


async def test_page_range_limits_extraction(mcp_server):
    """start_page/end_page limits which pages are extracted (fixture has 2 pages)."""
    async with Client(mcp_server) as client:
        result_p1 = await client.call_tool("read_file", {
            "source": FIXTURE_PDF,
            "start_page": 1,
            "end_page": 1,
        })
        result_p2 = await client.call_tool("read_file", {
            "source": FIXTURE_PDF,
            "start_page": 2,
            "end_page": 2,
        })

    text_p1 = json.loads(result_p1.content[0].text)["text"]
    text_p2 = json.loads(result_p2.content[0].text)["text"]
    assert text_p1 != text_p2
    assert "page two" in text_p2.lower()


async def test_single_page_read_pages_read_format(mcp_server):
    """Single-page read produces pages_read='N', not 'N-N'."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {
            "source": FIXTURE_PDF,
            "start_page": 1,
            "end_page": 1,
        })

    meta = json.loads(result.content[0].text)["metadata"]
    assert meta["pages_read"] == "1"


async def test_end_page_beyond_count_is_clamped(mcp_server):
    """end_page beyond page_count is clamped; pages_read reflects clamped value."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {
            "source": FIXTURE_PDF,
            "start_page": 1,
            "end_page": 9999,
        })

    data = json.loads(result.content[0].text)
    assert data["metadata"]["pages_read"] == "1-2"
    assert data["metadata"]["page_count"] == 2


async def test_start_page_beyond_count_raises(mcp_server):
    """start_page beyond page_count raises ToolError."""
    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {
                "source": FIXTURE_PDF,
                "start_page": 999,
            })


# ---------------------------------------------------------------------------
# Local text files
# ---------------------------------------------------------------------------

async def test_local_txt_file_returns_correct_shape(mcp_server, tmp_path):
    """Local .txt file returns correct JSON shape with null metadata."""
    content = "Hello from a text file."
    f = tmp_path / "readme.txt"
    f.write_text(content, encoding="utf-8")

    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": str(f)})

    data = json.loads(result.content[0].text)
    assert data["file_type"] == "text"
    assert data["text"] == content
    assert data["metadata"]["title"] is None
    assert data["metadata"]["page_count"] is None
    assert data["metadata"]["pages_read"] is None


async def test_local_md_file_returns_correct_shape(mcp_server, tmp_path):
    """Local .md file is treated as text."""
    f = tmp_path / "notes.md"
    f.write_text("# Heading\nSome markdown.", encoding="utf-8")

    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": str(f)})

    data = json.loads(result.content[0].text)
    assert data["file_type"] == "text"
    assert "Heading" in data["text"]


async def test_non_utf8_bytes_replaced(mcp_server, tmp_path):
    """Non-UTF-8 bytes in text file are replaced with U+FFFD, not raising."""
    f = tmp_path / "latin.txt"
    f.write_bytes(b"caf\xe9 au lait")  # \xe9 = é in latin-1, invalid utf-8

    async with Client(mcp_server) as client:
        result = await client.call_tool("read_file", {"source": str(f)})

    data = json.loads(result.content[0].text)
    assert data["file_type"] == "text"
    assert "\ufffd" in data["text"]


# ---------------------------------------------------------------------------
# Remote URL fetching
# ---------------------------------------------------------------------------

def _make_pdf_bytes() -> bytes:
    """Create a minimal valid PDF in memory using fitz."""
    doc = fitz.open()
    doc.insert_page(-1, text="Remote PDF content.", fontsize=11)
    return doc.tobytes()


async def test_remote_url_pdf_happy_path(mcp_server):
    """Remote https:// URL returning a PDF is fetched and parsed correctly."""
    pdf_bytes = _make_pdf_bytes()
    with respx.mock:
        respx.get("https://example.com/paper.pdf").mock(
            return_value=httpx.Response(200, content=pdf_bytes)
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool(
                "read_file", {"source": "https://example.com/paper.pdf"}
            )

    data = json.loads(result.content[0].text)
    assert data["file_type"] == "pdf"
    assert "Remote PDF" in data["text"]


async def test_remote_url_no_extension_treated_as_text(mcp_server):
    """Remote URL with no file extension defaults to text."""
    with respx.mock:
        respx.get("https://example.com/api/content").mock(
            return_value=httpx.Response(200, content=b"plain text response")
        )
        async with Client(mcp_server) as client:
            result = await client.call_tool(
                "read_file", {"source": "https://example.com/api/content"}
            )

    data = json.loads(result.content[0].text)
    assert data["file_type"] == "text"
    assert "plain text" in data["text"]


async def test_remote_url_404_raises_immediately(mcp_server):
    """404 raises ToolError immediately with no retry."""
    with respx.mock:
        route = respx.get("https://example.com/missing.pdf").mock(
            return_value=httpx.Response(404)
        )
        async with Client(mcp_server) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "read_file", {"source": "https://example.com/missing.pdf"}
                )

    assert route.call_count == 1


async def test_remote_url_500_retries_then_raises(mcp_server):
    """Three consecutive 500s exhaust retries and raise ToolError."""
    with patch("mcp_tools.file_reader.server.asyncio.sleep"):
        with respx.mock:
            route = respx.get("https://example.com/paper.pdf").mock(
                return_value=httpx.Response(500)
            )
            async with Client(mcp_server) as client:
                with pytest.raises(ToolError):
                    await client.call_tool(
                        "read_file", {"source": "https://example.com/paper.pdf"}
                    )

    assert route.call_count == 3


async def test_remote_url_500_recovers_on_third_attempt(mcp_server):
    """500 on first two attempts, success on third."""
    pdf_bytes = _make_pdf_bytes()
    with patch("mcp_tools.file_reader.server.asyncio.sleep"):
        with respx.mock:
            route = respx.get("https://example.com/paper.pdf")
            route.side_effect = [
                httpx.Response(500),
                httpx.Response(500),
                httpx.Response(200, content=pdf_bytes),
            ]
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "read_file", {"source": "https://example.com/paper.pdf"}
                )

    data = json.loads(result.content[0].text)
    assert data["file_type"] == "pdf"
    assert route.call_count == 3


# ---------------------------------------------------------------------------
# Corrupt PDF
# ---------------------------------------------------------------------------

async def test_corrupt_pdf_raises(mcp_server, tmp_path):
    """File with .pdf extension but corrupt content raises ToolError."""
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"this is not a valid pdf")

    async with Client(mcp_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("read_file", {"source": str(bad)})
