# mcp_tools/vector_db/tests/test_server.py
import pytest


@pytest.fixture
def mcp_server():
    from mcp_tools.vector_db.server import mcp
    return mcp


def test_chunk_text_splits_into_expected_count():
    """2500-char content with chunk_size=1000, overlap=0 produces 3 chunks."""
    from mcp_tools.vector_db.server import _chunk_text
    chunks = _chunk_text("X" * 2500, chunk_size=1000, overlap=0)
    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
    assert len(chunks[2]) == 500


def test_chunk_text_short_content_returns_single_chunk():
    """Content shorter than chunk_size produces exactly 1 chunk."""
    from mcp_tools.vector_db.server import _chunk_text
    chunks = _chunk_text("Short text", chunk_size=1000, overlap=0)
    assert len(chunks) == 1
    assert chunks[0] == "Short text"


def test_chunk_text_with_overlap_produces_correct_count():
    """2000-char content with chunk_size=1000, overlap=200 produces 3 chunks (sliding window)."""
    from mcp_tools.vector_db.server import _chunk_text
    # Step: 1000 - 200 = 800 per advance
    # chunk 1: [0, 1000), chunk 2: [800, 1800), chunk 3: [1600, 2000)
    chunks = _chunk_text("X" * 2000, chunk_size=1000, overlap=200)
    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
    assert len(chunks[2]) == 400  # remaining 400 chars
