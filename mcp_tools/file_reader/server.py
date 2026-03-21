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
# Delays (seconds) before attempt 2 and attempt 3. Attempt 1 is immediate.
BACKOFF_DELAYS = [1, 2]


def _check_path_allowed(path: str) -> None:
    """If FILE_READER_BASE_DIR is set, verify the path stays within it."""
    base_dir = os.environ.get("FILE_READER_BASE_DIR", "")
    if not base_dir:
        return  # no restriction configured
    import pathlib
    allowed = pathlib.Path(base_dir).resolve()
    resolved = pathlib.Path(path).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message=f"Path is outside the allowed base directory ({allowed})",
        ))


def _detect_file_type(source: str) -> str:
    """Return 'pdf' or 'text' based on file extension. Raises McpError for unsupported types."""
    is_url = source.startswith("https://")

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
    """Read a local file as bytes using a thread to avoid blocking the event loop."""
    def _read() -> bytes:
        with open(path, "rb") as f:
            return f.read()
    try:
        return await asyncio.to_thread(_read)
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

    if source.startswith("https://"):
        data = await _fetch_remote(source)
    else:
        _check_path_allowed(source)  # <-- add this line
        data = await _read_local(source)

    if file_type == "pdf":
        def _parse_pdf() -> dict:
            try:
                doc = fitz.open(stream=data, filetype="pdf")
            except Exception as e:
                raise RuntimeError(f"Failed to parse PDF: {e}")
            try:
                page_count = doc.page_count
                if start_page > page_count:
                    raise ValueError(f"start_page ({start_page}) exceeds page count ({page_count})")
                resolved_end = min(end_page, page_count) if end_page is not None else page_count
                text = "\n".join(doc[i].get_text() for i in range(start_page - 1, resolved_end))
                raw_meta = doc.metadata
                return {
                    "page_count": page_count,
                    "text": text,
                    "title": raw_meta.get("title") or None,  # coerce "" to None
                    "author": raw_meta.get("author") or None,
                    "pages_read": str(start_page) if start_page == resolved_end else f"{start_page}-{resolved_end}",
                }
            finally:
                doc.close()

        try:
            pdf_result = await asyncio.to_thread(_parse_pdf)
        except ValueError as e:
            raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))
        except RuntimeError as e:
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(e)))

        metadata = {
            "title": pdf_result["title"],
            "author": pdf_result["author"],
            "page_count": pdf_result["page_count"],
            "pages_read": pdf_result["pages_read"],
        }
        text = pdf_result["text"]
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
