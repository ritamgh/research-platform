# File Reader MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastMCP MCP tool server at port 9003 that reads PDFs and plain text files (local path or remote `https://` URL) and returns extracted text plus metadata.

**Architecture:** Thin FastMCP 2.x tool layer. PyMuPDF (fitz) for PDF parsing, httpx for remote URL fetching with retry. Mirrors `web_search` and `vector_db` tool patterns exactly — same FastMCP Client testing pattern, same retry loop, same McpError/ErrorData raising. No required environment variables.

**Tech Stack:** FastMCP 2.x, PyMuPDF (`pymupdf`), httpx, python-dotenv, pytest + pytest-asyncio, respx

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `mcp_tools/file_reader/__init__.py` | Create | Package marker |
| `mcp_tools/file_reader/requirements.txt` | Create | Dependencies |
| `mcp_tools/file_reader/pytest.ini` | Create | asyncio_mode = auto |
| `mcp_tools/file_reader/server.py` | Create | FastMCP + all tool logic |
| `mcp_tools/file_reader/main.py` | Create | Entry point, port 9003 |
| `mcp_tools/file_reader/tests/__init__.py` | Create | Test package marker |
| `mcp_tools/file_reader/tests/fixtures/sample.pdf` | Create (generated) | Integration test fixture |
| `mcp_tools/file_reader/tests/test_server.py` | Create | 24 unit tests |
| `mcp_tools/file_reader/tests/test_integration.py` | Create | 1 live test |
| `docs/CODEMAPS/mcp_tools.md` | Modify | Mark file_reader ✅ |
| `docs/CODEMAPS/architecture.md` | Modify | Mark file_reader ✅ Built |

---

## Codebase Context

This tool lives in `mcp_tools/file_reader/` alongside two existing tools that define the exact patterns to follow:

- `mcp_tools/web_search/server.py` — single `search_web` tool; httpx with `RETRYABLE_STATUS = {429, 500, 502, 503, 504}` and `BACKOFF_DELAYS = [1, 2]`; `McpError(ErrorData(code=..., message=...))` for all errors; returns `json.dumps(...)` string
- `mcp_tools/web_search/tests/test_server.py` — uses `FastMCP Client` in-process; `async with Client(mcp_server) as client: result = await client.call_tool(...)`, `result.content[0].text` for JSON; `pytest.raises(ToolError)` for errors; `respx` for HTTP mocking; patches `asyncio.sleep` to skip delays

Both tools are tested with `pytest -v` run from within the tool directory (e.g. `cd mcp_tools/file_reader && pytest`).

**Before writing any PyMuPDF code:** Look up the current API via Context7:
```
mcp__context7__resolve-library-id (libraryName="PyMuPDF")
mcp__context7__query-docs (libraryId=..., query="open from bytes, page_count, get_text, metadata, create PDF, FitzError")
```

---

## Task 1: Scaffold

**Files:**
- Create: `mcp_tools/file_reader/__init__.py`
- Create: `mcp_tools/file_reader/requirements.txt`
- Create: `mcp_tools/file_reader/pytest.ini`
- Create: `mcp_tools/file_reader/tests/__init__.py`
- Create: `mcp_tools/file_reader/tests/fixtures/sample.pdf`

This task is mechanical — no logic, no tests. Just create config files and generate the PDF fixture.

- [ ] **Step 1: Create package files**

```bash
mkdir -p mcp_tools/file_reader/tests/fixtures
touch mcp_tools/file_reader/__init__.py
touch mcp_tools/file_reader/tests/__init__.py
```

- [ ] **Step 2: Create `requirements.txt`**

`mcp_tools/file_reader/requirements.txt`:
```
fastmcp>=2.0
pymupdf>=1.24
httpx>=0.27
python-dotenv>=1.0

# test dependencies
pytest>=8.0
pytest-asyncio>=0.24
respx>=0.21
```

- [ ] **Step 3: Create `pytest.ini`**

`mcp_tools/file_reader/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
markers =
    integration: marks tests as integration tests
```

- [ ] **Step 4: Install dependencies**

```bash
cd mcp_tools/file_reader && pip install -r requirements.txt
```

Expected: all packages installed without error. Verify with `python -c "import fitz; print(fitz.__version__)"`.

- [ ] **Step 5: Generate the fixture PDF**

Run this Python snippet to create `tests/fixtures/sample.pdf`:

```python
import fitz  # pymupdf

doc = fitz.open()
doc.insert_page(-1,
    text="This is a sample PDF document for testing the file_reader MCP tool.\n"
         "It contains content for validating text extraction.",
    fontsize=11,
)
doc.insert_page(-1,
    text="Page two content for testing page range extraction.",
    fontsize=11,
)
doc.set_metadata({"title": "Sample Test PDF", "author": "Test Author"})
doc.save("mcp_tools/file_reader/tests/fixtures/sample.pdf")
doc.close()
print("Created sample.pdf")
```

Run from the repo root: `python -c "<paste snippet above>"`

Expected: file `mcp_tools/file_reader/tests/fixtures/sample.pdf` created, ~3-5 KB.

- [ ] **Step 6: Commit**

```bash
git add mcp_tools/file_reader/
git commit -m "chore: scaffold mcp_tools/file_reader module"
```

---

## Task 2: `server.py` — helpers + `read_file` tool with all unit tests (TDD)

**Files:**
- Create: `mcp_tools/file_reader/tests/test_server.py`
- Create: `mcp_tools/file_reader/server.py`

Full TDD cycle: write all 24 tests first (RED), then implement `server.py` until all pass (GREEN).

**Before writing any code:** Look up PyMuPDF's current API via Context7 (see Codebase Context above).

### Step 1–4: Write the failing tests

- [ ] **Step 1: Create `test_server.py` with fixture and input validation tests**

`mcp_tools/file_reader/tests/test_server.py`:
```python
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
    # Create a PDF with no metadata
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
    # Pages have different content
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
    assert data["metadata"]["pages_read"] == "1-2"  # clamped to actual page count (2)
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
    assert "\ufffd" in data["text"]  # replacement character present


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

    assert route.call_count == 1  # no retry


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

    assert route.call_count == 3  # all 3 attempts fired


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
```

- [ ] **Step 2: Run tests — verify all fail (server.py doesn't exist yet)**

```bash
cd mcp_tools/file_reader && pytest tests/test_server.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError` — `server.py` doesn't exist yet. That's correct (RED phase).

- [ ] **Step 3: Implement `server.py`**

**Before writing:** Verify PyMuPDF API with Context7 (`mcp__context7__resolve-library-id` → `mcp__context7__query-docs`).

`mcp_tools/file_reader/server.py`:
```python
# mcp_tools/file_reader/server.py
import asyncio
import json
import os
from urllib.parse import urlparse

import fitz  # PyMuPDF
import httpx
from fastmcp import FastMCP
from mcp.shared.exceptions import McpError, ErrorData
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, INVALID_REQUEST

mcp = FastMCP("file-reader-tool")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BACKOFF_DELAYS = [1, 2]


def _detect_file_type(source: str) -> str:
    """Return 'pdf' or 'text' based on file extension. Raises McpError for unsupported types."""
    is_url = source.startswith("https://")

    # Strip query string and fragment from URLs before extension check
    if is_url:
        path = urlparse(source).path
    else:
        path = source

    _, ext = os.path.splitext(path)
    ext = ext.lower()

    if ext == ".pdf":
        return "pdf"
    elif ext in (".txt", ".md"):
        return "text"
    elif ext == "" and is_url:
        # Extensionless URL (e.g. API endpoint) defaults to text
        return "text"
    elif ext == "":
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="Local paths must have a supported extension: .pdf, .txt, .md",
        ))
    else:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message=f"Unsupported file type '{ext}'. Supported: .pdf, .txt, .md",
        ))


async def _read_local(path: str) -> bytes:
    """Read a local file as bytes. Raises McpError on I/O failures."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=f"File not found: {path}"))
    except PermissionError:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=f"Permission denied: {path}"))
    except OSError as e:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(e)))


async def _fetch_remote(url: str) -> bytes:
    """Fetch a remote https:// URL as bytes. Retries on transient errors."""
    last_error = "unknown error"
    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            if attempt > 0:
                await asyncio.sleep(BACKOFF_DELAYS[attempt - 1])
            try:
                resp = await client.get(url, timeout=30.0)
                if resp.status_code in RETRYABLE_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                    continue
                if resp.status_code >= 400:
                    raise McpError(ErrorData(
                        code=INVALID_REQUEST,
                        message=f"HTTP {resp.status_code} fetching {url}",
                    ))
                return resp.content
            except McpError:
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = f"{type(e).__name__}: {e}"
                continue
    raise McpError(ErrorData(
        code=INTERNAL_ERROR,
        message=f"Failed to fetch {url} after 3 attempts: {last_error}",
    ))


@mcp.tool
async def read_file(
    source: str,
    start_page: int = 1,
    end_page: int | None = None,
) -> str:
    """Read a PDF or plain text file from a local path or remote https:// URL."""
    # Input validation
    if not source or not source.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="source must not be empty"))
    if source.startswith("http://"):
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="Only https:// URLs are supported, not http://",
        ))
    if start_page < 1:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="start_page must be >= 1"))
    if end_page is not None and end_page < start_page:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="end_page must be >= start_page",
        ))

    file_type = _detect_file_type(source)

    # Fetch bytes
    if source.startswith("https://"):
        data = await _fetch_remote(source)
    else:
        data = await _read_local(source)

    if file_type == "pdf":
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to parse PDF: {e}"))

        page_count = doc.page_count
        if start_page > page_count:
            raise McpError(ErrorData(
                code=INVALID_PARAMS,
                message=f"start_page ({start_page}) exceeds page count ({page_count})",
            ))

        resolved_end = min(end_page, page_count) if end_page is not None else page_count
        text = "\n".join(doc[i].get_text() for i in range(start_page - 1, resolved_end))

        raw_meta = doc.metadata
        title = raw_meta.get("title") or None
        author = raw_meta.get("author") or None
        pages_read = str(start_page) if start_page == resolved_end else f"{start_page}-{resolved_end}"

        metadata = {
            "title": title,
            "author": author,
            "page_count": page_count,
            "pages_read": pages_read,
        }
    else:
        text = data.decode("utf-8", errors="replace")
        metadata = {
            "title": None,
            "author": None,
            "page_count": None,
            "pages_read": None,
        }

    return json.dumps({
        "source": source,
        "file_type": file_type,
        "text": text,
        "metadata": metadata,
    })
```

- [ ] **Step 4: Run all unit tests — verify all pass**

```bash
cd mcp_tools/file_reader && pytest tests/test_server.py -v
```

Expected: 24 tests pass. If any fail, debug before proceeding.

- [ ] **Step 5: Commit**

```bash
git add mcp_tools/file_reader/server.py mcp_tools/file_reader/tests/test_server.py
git commit -m "feat: add file_reader server with read_file tool and 24 unit tests"
```

---

## Task 3: `main.py`, integration test, and codemaps

**Files:**
- Create: `mcp_tools/file_reader/main.py`
- Create: `mcp_tools/file_reader/tests/test_integration.py`
- Modify: `docs/CODEMAPS/mcp_tools.md`
- Modify: `docs/CODEMAPS/architecture.md`

This task is mechanical for `main.py` and scaffold for the integration test.

- [ ] **Step 1: Create `main.py`**

`mcp_tools/file_reader/main.py`:
```python
# mcp_tools/file_reader/main.py
from dotenv import load_dotenv

load_dotenv()

from mcp_tools.file_reader.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9003)
```

No required env vars — no startup validation needed.

- [ ] **Step 2: Create `test_integration.py`**

`mcp_tools/file_reader/tests/test_integration.py`:
```python
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
```

- [ ] **Step 3: Run integration test**

```bash
cd mcp_tools/file_reader && pytest tests/test_integration.py -v
```

Expected: `1 passed`. No env vars required — runs against the bundled fixture.

- [ ] **Step 4: Run the full test suite**

```bash
cd mcp_tools/file_reader && pytest -v
```

Expected: 25 tests pass (24 unit + 1 integration).

- [ ] **Step 5: Update `docs/CODEMAPS/mcp_tools.md`**

In `docs/CODEMAPS/mcp_tools.md`, replace the `file_reader ⬜` entry:

```
## file_reader ⬜ (port 9003)
Tools: PDF/text parsing — wraps PyMuPDF
```

with:

```markdown
## file_reader ✅ (port 9003)

```
main.py  →  load_dotenv() → mcp.run(transport="http", port=9003)
server.py →  FastMCP("file-reader-tool")
              └── read_file(source, start_page=1, end_page=None) → str (JSON)
                    ├── validate: source non-empty, not http://, start_page ≥ 1, end_page ≥ start_page
                    ├── _detect_file_type(source) — extension-based (.pdf → pdf, .txt/.md → text, no-ext URL → text)
                    ├── _read_local(path) → bytes — FileNotFoundError/PermissionError/OSError → McpError
                    ├── _fetch_remote(url) → bytes — RETRYABLE_STATUS {429,500,502,503,504}, 3 attempts, backoff [1s,2s]
                    ├── PDF path: fitz.open(stream=...) → page_count, get_text(), metadata{title,author}
                    │     end_page clamped to page_count; pages_read: "N" or "start-end" from resolved values
                    └── text path: bytes.decode("utf-8", errors="replace") → null metadata
```

**Response shape:**
```json
{"source": "...", "file_type": "pdf|text", "text": "...", "metadata": {"title", "author", "page_count", "pages_read"}}
```

**Key files:**
- `mcp_tools/file_reader/server.py` — tool logic (~130 lines)
- `mcp_tools/file_reader/main.py` — entrypoint, port 9003
- `mcp_tools/file_reader/tests/test_server.py` — 24 unit tests
- `mcp_tools/file_reader/tests/test_integration.py` — 1 integration test (no env vars required)

**Env vars:** None required
```

- [ ] **Step 6: Update `docs/CODEMAPS/architecture.md`**

Find the line marking `file_reader` as planned and change it to `✅ Built`. Read the file first to find the exact text, then edit it.

- [ ] **Step 7: Commit**

```bash
git add mcp_tools/file_reader/main.py \
        mcp_tools/file_reader/tests/test_integration.py \
        docs/CODEMAPS/mcp_tools.md \
        docs/CODEMAPS/architecture.md
git commit -m "feat: add file_reader main.py, integration test, and update codemaps"
```
