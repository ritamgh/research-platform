# File Reader MCP Tool Design

**Goal:** Build a FastMCP tool server that reads PDF and plain text files (local or remote URL) and returns extracted text plus metadata, to be consumed by research and RAG agents.

**Architecture:** Thin MCP tool layer — PyMuPDF for PDF parsing, httpx for remote fetch, no framework abstractions. Mirrors the `web_search` and `vector_db` tool patterns exactly. No required environment variables.

**Tech Stack:** FastMCP 2.x, PyMuPDF (fitz), httpx, python-dotenv, pytest + pytest-asyncio

---

## File Structure

```
mcp_tools/file_reader/
├── server.py          # FastMCP instance + tool logic (~130 lines)
├── main.py            # load_dotenv, mcp.run(port=9003)
├── requirements.txt   # dependencies
├── pytest.ini         # asyncio_mode = auto
├── __init__.py
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   └── sample.pdf      # small bundled PDF for integration test
    ├── test_server.py      # unit tests (mocked filesystem + httpx)
    └── test_integration.py # live test with bundled PDF fixture
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

Reads a PDF or plain text file from a local path or remote `https://` URL and returns extracted text with metadata.

**Parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `source` | `str` | required | non-empty; local filesystem path or `https://` URL only |
| `start_page` | `int` | `1` | ≥ 1; PDF only, ignored for text files |
| `end_page` | `int \| None` | `None` | ≥ `start_page` if set; silently clamped to `page_count` if it exceeds the document length; PDF only |

**Only `https://` URLs are supported.** Passing an `http://` URL raises `INVALID_PARAMS` immediately with a clear message. Passing `end_page` larger than `page_count` is safe — it is clamped to the last page rather than raising an error.

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

`pages_read` format: `"start-end"` when `start != end` (e.g. `"1-10"`), or `"N"` when a single page is read (e.g. `"5"`). For text files, `pages_read` is `null`.

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
├── RETRYABLE_STATUS = {429, 500, 502, 503, 504}   # mirrors web_search pattern exactly
├── BACKOFF_DELAYS = [1, 2]
│
├── _detect_file_type(source) -> "pdf" | "text"
│     — strips query string and fragment from URLs before checking extension
│     — .pdf → "pdf"
│     — .txt, .md → "text"
│     — no extension AND source is an https:// URL → "text" (plain HTTP responses)
│     — no extension AND source is a local path → raise McpError(INVALID_PARAMS)
│     — any other extension (.docx, .xlsx, .png, etc.) → raise McpError(INVALID_PARAMS)
│
├── _fetch_remote(url) -> bytes
│     — httpx.AsyncClient with 30s timeout
│     — retry loop: 3 attempts, backoff [1s, 2s] (asyncio.sleep, same as web_search)
│     — on each attempt:
│         1. if status in RETRYABLE_STATUS → retry (includes 429)
│         2. if TimeoutException or ConnectError → retry
│         3. if any other 4xx → raise McpError(INVALID_REQUEST) immediately (no retry)
│         4. success → return response.content
│     — exhausted retries → raise McpError(INTERNAL_ERROR)
│
├── _read_local(path) -> bytes
│     — reads file from filesystem in binary mode
│     — FileNotFoundError → raise McpError(INVALID_PARAMS, "File not found: ...")
│     — PermissionError → raise McpError(INVALID_PARAMS, "Permission denied: ...")
│     — other OSError → raise McpError(INTERNAL_ERROR, str(e))
│
└── read_file(source, start_page=1, end_page=None) -> str (JSON)
      ├── validate: source non-empty → INVALID_PARAMS
      ├── validate: source starts with "http://" → INVALID_PARAMS ("only https:// URLs are supported")
      ├── validate: start_page ≥ 1 → INVALID_PARAMS
      ├── validate: end_page ≥ start_page if set → INVALID_PARAMS
      ├── detect file type via _detect_file_type(source)
      ├── fetch bytes:
      │     _fetch_remote() if source starts with "https://"
      │     _read_local() otherwise (local path)
      ├── if pdf:
      │     ├── open with fitz.open(stream=bytes, filetype="pdf")
      │     │     fitz.FitzError or Exception (corrupt/unreadable) → raise McpError(INTERNAL_ERROR)
      │     ├── validate start_page ≤ doc.page_count → raise INVALID_PARAMS if not
      │     ├── resolve end_page: min(end_page, doc.page_count) if set, else doc.page_count
      │     ├── extract text: "\n".join(page.get_text() for page in doc[start_page-1:end_page])
      │     ├── extract metadata: doc.metadata → {title, author}; empty string → null
      │     ├── compute pages_read from resolved (clamped) values: "N" if resolved_start==resolved_end, else "resolved_start-resolved_end"
      │     └── return JSON
      └── if text:
            ├── decode bytes as UTF-8 with errors="replace" (non-UTF-8 bytes replaced with U+FFFD)
            └── metadata: all null
```

---

## Supported File Types

| Extension | `file_type` | Parser |
|---|---|---|
| `.pdf` | `pdf` | PyMuPDF (fitz) |
| `.txt` | `text` | UTF-8 decode (errors="replace") |
| `.md` | `text` | UTF-8 decode (errors="replace") |
| No extension (https:// URL only) | `text` | UTF-8 decode (errors="replace") |
| No extension (local path) | — | raise `INVALID_PARAMS` |
| Any other extension | — | raise `INVALID_PARAMS` |

**URL extension detection:** strip query strings and fragments before checking extension (e.g. `https://arxiv.org/pdf/2301.00001.pdf?download=true` → `.pdf`).

---

## Error Handling

| Condition | Code | Retry |
|---|---|---|
| Empty `source` | `INVALID_PARAMS` | — |
| `http://` URL (non-https scheme) | `INVALID_PARAMS` | — |
| `start_page < 1` | `INVALID_PARAMS` | — |
| `end_page < start_page` | `INVALID_PARAMS` | — |
| Unsupported file extension | `INVALID_PARAMS` | — |
| Local file not found | `INVALID_PARAMS` | — |
| Local file permission denied | `INVALID_PARAMS` | — |
| Other local read error (OSError) | `INTERNAL_ERROR` | — |
| Local path with no extension | `INVALID_PARAMS` | — |
| `start_page` beyond PDF page count | `INVALID_PARAMS` | — |
| `end_page` beyond PDF page count | — (clamped silently) | — |
| HTTP 429 / 5xx / ConnectError / timeout | `INTERNAL_ERROR` | 3 attempts, backoff [1s, 2s] |
| HTTP 4xx (not 429) on remote URL | `INVALID_REQUEST` | No |
| Corrupt/unreadable PDF (fitz error) | `INTERNAL_ERROR` | — |

---

## Environment Variables

None required. The tool works without any API keys.

---

## Testing

### Unit tests (`test_server.py`, ~24 tests)

All filesystem reads and HTTP calls mocked. Uses `FastMCP Client` + `pytest-asyncio`, same pattern as `web_search` and `vector_db`. Tests patch `asyncio.sleep` to avoid real delays.

| Test | Verifies |
|---|---|
| Empty `source` raises `ToolError` | input validation |
| `http://` URL raises `ToolError` with clear message | scheme validation |
| `start_page=0` raises `ToolError` | bounds check |
| `end_page < start_page` raises `ToolError` | bounds check |
| Unsupported extension (`.docx`) raises `ToolError` | type detection |
| Local file not found raises `ToolError` | filesystem error |
| Local PDF happy path returns correct shape | happy path |
| Text extraction matches expected content | PDF parsing |
| Metadata fields present (title, author, page_count) | metadata extraction |
| Empty PDF metadata fields returned as null, not empty string | metadata normalization |
| Page range limits extraction to requested pages | page range |
| Single-page read produces `pages_read: "N"` format | pages_read format |
| `end_page` beyond page count is clamped; `pages_read` reflects clamped value | end_page clamping |
| `start_page` beyond page count raises `ToolError` | bounds check |
| Local `.txt` file returns correct shape | text happy path |
| Local `.md` file returns correct shape | text happy path |
| Non-UTF-8 bytes in text file returned with replacement chars | UTF-8 fallback |
| Remote URL PDF fetch happy path | URL fetch + PDF |
| Remote URL text fetch (no extension) happy path | extensionless URL → text |
| Local path with no extension raises `ToolError` | extensionless local path |
| Remote URL 404 raises `ToolError` immediately (no retry) | no retry on 4xx |
| Remote URL 500 retries 3× then raises `ToolError` | retry exhaustion |
| Remote URL 500 recovers on 3rd attempt | retry success |
| Corrupt PDF raises `ToolError` | parse error handling |

### Integration test (`test_integration.py`, 1 test)

No env vars required — always runs. Reads the bundled `tests/fixtures/sample.pdf`, asserts text is non-empty and `metadata.page_count` is a positive integer.
