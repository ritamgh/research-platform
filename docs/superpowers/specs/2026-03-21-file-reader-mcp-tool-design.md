# File Reader MCP Tool Design

**Goal:** Build a FastMCP tool server that reads PDF and plain text files (local or remote URL) and returns extracted text plus metadata, to be consumed by research and RAG agents.

**Architecture:** Thin MCP tool layer — PyMuPDF for PDF parsing, httpx for remote fetch, no framework abstractions. Mirrors the `web_search` and `vector_db` tool patterns exactly. No required environment variables.

**Tech Stack:** FastMCP 2.x, PyMuPDF (fitz), httpx, python-dotenv, pytest + pytest-asyncio

---

## File Structure

```
mcp_tools/file_reader/
├── server.py          # FastMCP instance + tool logic (~120 lines)
├── main.py            # load_dotenv, mcp.run(port=9003)
├── requirements.txt   # dependencies
├── pytest.ini         # asyncio_mode = auto
├── __init__.py
└── tests/
    ├── __init__.py
    ├── test_server.py      # unit tests (mocked filesystem + httpx)
    └── test_integration.py # live test with a real PDF fixture
```

---

## `main.py`

Mirrors `web_search/main.py` — no required env vars for this tool:

```python
import os, sys
from dotenv import load_dotenv

load_dotenv()

from mcp_tools.file_reader.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9003)
```

---

## Tool

### `read_file`

Reads a PDF or plain text file from a local path or remote URL and returns extracted text with metadata.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `source` | `str` | required | non-empty; local filesystem path or `https://` URL |
| `start_page` | `int` | `1` | ≥ 1; PDF only, ignored for text files |
| `end_page` | `int \| None` | `None` | ≥ `start_page` if set; PDF only |

**Response shape:**
```json
{
  "source": "/path/to/paper.pdf",
  "file_type": "pdf",
  "text": "...extracted text...",
  "metadata": {
    "title": "Example Paper",
    "author": "Jane Smith",
    "page_count": 42,
    "pages_read": "1-10"
  }
}
```

For plain text files:
```json
{
  "source": "https://example.com/readme.txt",
  "file_type": "text",
  "text": "...file contents...",
  "metadata": {
    "title": null,
    "author": null,
    "page_count": null,
    "pages_read": null
  }
}
```

---

## Internal Structure (`server.py`)

```
FastMCP("file-reader-tool")
├── _detect_file_type(source) -> "pdf" | "text"
│     — extension-based: .pdf → "pdf"; .txt, .md, and all others → "text"
│     — unsupported types (e.g. .docx, .xlsx) → raise McpError(INVALID_PARAMS)
├── _fetch_remote(url) -> bytes
│     — httpx.AsyncClient with 30s timeout
│     — retry loop: 3 attempts, backoff [1s, 2s]
│     — 4xx → raise McpError(INVALID_REQUEST) immediately (no retry)
│     — 5xx / timeout → retry; exhaustion → raise McpError(INTERNAL_ERROR)
├── _read_local(path) -> bytes
│     — reads file from filesystem
│     — FileNotFoundError → raise McpError(INVALID_PARAMS)
└── read_file(source, start_page=1, end_page=None) -> str (JSON)
      ├── validate: source non-empty
      ├── validate: start_page ≥ 1
      ├── validate: end_page ≥ start_page if set
      ├── detect file type via _detect_file_type(source)
      ├── fetch bytes: _fetch_remote() if source starts with "https://" else _read_local()
      ├── if pdf:
      │     ├── open with fitz.open(stream=bytes, filetype="pdf")
      │     ├── validate start_page ≤ page_count → raise INVALID_PARAMS if not
      │     ├── clamp end_page to page_count if None or exceeds
      │     ├── extract text: concatenate page.get_text() for pages in range
      │     ├── extract metadata: doc.metadata (title, author)
      │     └── fitz error (corrupt PDF) → raise McpError(INTERNAL_ERROR)
      └── if text:
            ├── decode bytes as UTF-8
            └── metadata: all null
```

---

## Supported File Types

| Extension | `file_type` | Parser |
|---|---|---|
| `.pdf` | `pdf` | PyMuPDF (fitz) |
| `.txt` | `text` | UTF-8 decode |
| `.md` | `text` | UTF-8 decode |
| Any other extension | — | raise `INVALID_PARAMS` |

**Note:** URLs without extensions default to `text` (e.g. plain HTTP responses). URLs ending in `.pdf` are treated as PDF.

---

## Error Handling

| Condition | Code | Retry |
|---|---|---|
| Empty `source` | `INVALID_PARAMS` | — |
| `start_page < 1` | `INVALID_PARAMS` | — |
| `end_page < start_page` | `INVALID_PARAMS` | — |
| Unsupported file extension | `INVALID_PARAMS` | — |
| Local file not found | `INVALID_PARAMS` | — |
| `start_page` beyond PDF page count | `INVALID_PARAMS` | — |
| HTTP 4xx on remote URL | `INVALID_REQUEST` | No |
| HTTP 5xx / timeout on remote URL | `INTERNAL_ERROR` | 3 attempts, backoff [1s, 2s] |
| Corrupt/unreadable PDF | `INTERNAL_ERROR` | — |

---

## Environment Variables

None required. The tool works without any API keys.

---

## Testing

### Unit tests (`test_server.py`, ~18 tests)

All filesystem reads and HTTP calls mocked. Uses `FastMCP Client` + `pytest-asyncio`, same pattern as `web_search` and `vector_db`.

| Test | Verifies |
|---|---|
| Empty `source` raises `ToolError` | input validation |
| `start_page=0` raises `ToolError` | bounds check |
| `end_page < start_page` raises `ToolError` | bounds check |
| Unsupported extension raises `ToolError` | type detection |
| Local file not found raises `ToolError` | filesystem error |
| Local PDF happy path returns correct shape | happy path |
| Text extraction matches expected content | PDF parsing |
| Metadata fields present (title, author, page_count) | metadata extraction |
| Page range limits extraction to requested pages | page range |
| `start_page` beyond page count raises `ToolError` | bounds check |
| Local `.txt` file returns correct shape | text happy path |
| Local `.md` file returns correct shape | text happy path |
| Remote URL PDF fetch happy path | URL fetch + PDF |
| Remote URL text fetch happy path | URL fetch + text |
| Remote URL 404 raises `ToolError` immediately | no retry on 4xx |
| Remote URL 500 retries 3× then raises `ToolError` | retry exhaustion |
| Remote URL 500 recovers on 3rd attempt | retry success |
| Corrupt PDF raises `ToolError` | parse error handling |

### Integration test (`test_integration.py`, 1 test)

No env vars required — always runs. Reads a small bundled PDF fixture in `tests/fixtures/`, asserts text is non-empty and metadata contains `page_count`.
