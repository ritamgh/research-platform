"""Unit tests for the RAG agent."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


MOCK_HITS = json.dumps([
    {"content": "Attention mechanisms allow models to focus on relevant parts.", "source": "paper1.pdf"},
    {"content": "Transformers use multi-head self-attention.", "source": "paper2.pdf"},
])

MOCK_EMPTY = json.dumps([])
MOCK_INVALID_JSON = "Not JSON"


class TestMcpClient:
    def test_module_imports(self):
        from agents.rag import mcp_client
        assert callable(mcp_client.search_documents)
        assert callable(mcp_client.read_file)

    def test_url_env_vars(self, monkeypatch):
        monkeypatch.setenv("VECTOR_DB_MCP_URL", "http://localhost:9002")
        monkeypatch.setenv("FILE_READER_MCP_URL", "http://localhost:9003")
        import importlib
        import agents.rag.mcp_client as mod
        importlib.reload(mod)
        assert mod.VECTOR_DB_MCP_URL == "http://localhost:9002"
        assert mod.FILE_READER_MCP_URL == "http://localhost:9003"


class TestRunRagLookup:
    @pytest.mark.asyncio
    async def test_returns_string_with_hits(self):
        async def mock_search(query, top_k=5):
            return MOCK_HITS

        with patch("agents.rag.agent._get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.acomplete.return_value = MagicMock(__str__=lambda s: "Synthesised answer")
            mock_get_llm.return_value = mock_llm

            from agents.rag.agent import run_rag_lookup
            result = await run_rag_lookup("What are attention mechanisms?", search_fn=mock_search)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_returns_no_docs_message_when_empty(self):
        async def mock_search(query, top_k=5):
            return MOCK_EMPTY

        from agents.rag.agent import run_rag_lookup
        result = await run_rag_lookup("Obscure topic", search_fn=mock_search)

        assert "No relevant documents" in result

    @pytest.mark.asyncio
    async def test_handles_invalid_json_from_mcp(self):
        async def mock_search(query, top_k=5):
            return MOCK_INVALID_JSON

        with patch("agents.rag.agent._get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.acomplete.return_value = MagicMock(__str__=lambda s: "Fallback answer")
            mock_get_llm.return_value = mock_llm

            from agents.rag.agent import run_rag_lookup
            result = await run_rag_lookup("Some query", search_fn=mock_search)

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sources_appended_to_result(self):
        async def mock_search(query, top_k=5):
            return MOCK_HITS

        with patch("agents.rag.agent._get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.acomplete.return_value = MagicMock(__str__=lambda s: "Answer text")
            mock_get_llm.return_value = mock_llm

            from agents.rag.agent import run_rag_lookup
            result = await run_rag_lookup("What are transformers?", search_fn=mock_search)

        assert "Sources consulted" in result


class TestRagServerEndpoints:
    @pytest.fixture
    def client(self):
        from agents.rag.main import build_app
        from fastapi.testclient import TestClient
        return TestClient(build_app())

    def test_agent_card_endpoint(self, client):
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "rag-agent"
        assert any(s["id"] == "rag_lookup" for s in data["skills"])

    def test_card_json_valid(self):
        import json
        from pathlib import Path
        card = json.loads((Path(__file__).parent.parent / "agent_card.json").read_text())
        assert card["name"] == "rag-agent"
        assert card["skills"][0]["id"] == "rag_lookup"
