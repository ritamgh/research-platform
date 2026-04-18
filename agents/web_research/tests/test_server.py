"""Unit tests for the web_research ADK agent server (main.py)."""
import pytest
from unittest.mock import AsyncMock, patch


# --- ADK Agent object ---

class TestWebResearchAgent:
    def test_agent_name(self):
        from agents.web_research.main import agent
        assert agent.name == "web_research"

    def test_agent_description(self):
        from agents.web_research.main import agent
        assert "web" in agent.description.lower()

    def test_agent_has_tool(self):
        from agents.web_research.main import agent
        assert len(agent.tools) == 1

    def test_app_is_starlette(self):
        from starlette.applications import Starlette
        from agents.web_research.main import app
        assert isinstance(app, Starlette)


# --- A2A Server endpoints ---

class TestA2AServerEndpoints:
    @pytest.fixture
    def client(self):
        from starlette.testclient import TestClient
        from agents.web_research.main import app
        # Use context manager to trigger lifespan startup (routes registered there)
        with TestClient(app) as c:
            yield c

    def test_agent_card_endpoint(self, client):
        response = client.get("/.well-known/agent-card.json")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "skills" in data

    def test_rpc_endpoint_exists(self, client):
        # The A2A JSON-RPC endpoint should return 4xx for malformed requests, not 404
        response = client.post("/", json={})
        assert response.status_code != 404


# --- Tool wrapper ---

class TestSearchWebTool:
    @pytest.mark.asyncio
    async def test_search_web_delegates_to_run_web_research(self):
        from agents.web_research.main import search_web

        with patch(
            "agents.web_research.main.run_web_research",
            new_callable=AsyncMock,
            return_value="Web result",
        ) as mock_run:
            result = await search_web("What is RAG?")

        mock_run.assert_awaited_once_with("What is RAG?")
        assert result == "Web result"

    @pytest.mark.asyncio
    async def test_search_web_returns_string(self):
        from agents.web_research.main import search_web

        with patch(
            "agents.web_research.main.run_web_research",
            new_callable=AsyncMock,
            return_value="Some result text",
        ):
            result = await search_web("any query")

        assert isinstance(result, str)
