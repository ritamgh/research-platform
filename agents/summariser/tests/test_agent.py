"""Unit tests for the summariser agent."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


MOCK_CRED_HIGH = json.dumps({
    "url": "https://arxiv.org/abs/2001.00001",
    "credibility_score": 0.9,
    "tier": "academic",
})

MOCK_CRED_LOW = json.dumps({
    "url": "https://random-blog.io/post",
    "credibility_score": 0.2,
    "tier": "unknown",
})


class TestMcpClient:
    def test_module_imports(self):
        from agents.summariser import mcp_client
        assert callable(mcp_client.check_credibility)
        assert callable(mcp_client.check_reachability)

    def test_url_env_var(self, monkeypatch):
        monkeypatch.setenv("CITATION_CHECKER_MCP_URL", "http://localhost:9004")
        import importlib
        import agents.summariser.mcp_client as mod
        importlib.reload(mod)
        assert mod.CITATION_CHECKER_MCP_URL == "http://localhost:9004"


class TestExtractUrls:
    def test_extracts_https_url(self):
        from agents.summariser.agent import _extract_urls
        text = "See https://arxiv.org/paper for details"
        urls = _extract_urls(text)
        assert "https://arxiv.org/paper" in urls

    def test_extracts_multiple_urls(self):
        from agents.summariser.agent import _extract_urls
        text = "Sources: https://a.com and https://b.org/path"
        urls = _extract_urls(text)
        assert len(urls) == 2

    def test_deduplicates_urls(self):
        from agents.summariser.agent import _extract_urls
        text = "https://a.com https://a.com"
        urls = _extract_urls(text)
        assert urls.count("https://a.com") == 1

    def test_returns_empty_for_no_urls(self):
        from agents.summariser.agent import _extract_urls
        assert _extract_urls("no urls here") == []


class TestRunSummariser:
    @pytest.mark.asyncio
    async def test_returns_string(self):
        async def mock_cred(url):
            return MOCK_CRED_HIGH

        with patch("agents.summariser.agent._get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Final synthesised answer")]
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            from agents.summariser.agent import run_summariser
            result = await run_summariser(
                query="What is RAG?",
                web_findings="RAG stands for retrieval augmented generation https://arxiv.org/1",
                rag_findings="Documents mention RAG improves factuality",
                credibility_fn=mock_cred,
            )

        assert isinstance(result, str)
        assert "Final synthesised answer" in result

    @pytest.mark.asyncio
    async def test_works_with_no_findings(self):
        async def mock_cred(url):
            return MOCK_CRED_LOW

        with patch("agents.summariser.agent._get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="General answer")]
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            from agents.summariser.agent import run_summariser
            result = await run_summariser(
                query="What is AI?",
                credibility_fn=mock_cred,
            )

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_credibility_check_called_for_urls(self):
        cred_calls = []

        async def mock_cred(url):
            cred_calls.append(url)
            return MOCK_CRED_HIGH

        with patch("agents.summariser.agent._get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Answer")]
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            from agents.summariser.agent import run_summariser
            await run_summariser(
                query="test",
                web_findings="See https://arxiv.org/abs/1234 for details",
                credibility_fn=mock_cred,
            )

        assert "https://arxiv.org/abs/1234" in cred_calls


class TestSummariserServerEndpoints:
    @pytest.fixture
    def client(self):
        from agents.summariser.main import build_app
        from fastapi.testclient import TestClient
        return TestClient(build_app())

    def test_agent_card_endpoint(self, client):
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "summariser-agent"
        assert any(s["id"] == "summarise" for s in data["skills"])

    def test_card_json_valid(self):
        import json
        from pathlib import Path
        card = json.loads((Path(__file__).parent.parent / "agent_card.json").read_text())
        assert card["skills"][0]["id"] == "summarise"
