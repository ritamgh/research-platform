"""Unit tests for the web_research A2A server (main.py)."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# --- Agent Card ---

class TestAgentCard:
    def test_card_json_exists(self):
        card_path = Path(__file__).parent.parent / "agent_card.json"
        assert card_path.exists()

    def test_card_json_valid(self):
        card_path = Path(__file__).parent.parent / "agent_card.json"
        card = json.loads(card_path.read_text())
        assert card["name"] == "web-research-agent"
        assert "skills" in card
        assert len(card["skills"]) > 0
        assert card["skills"][0]["id"] == "web_research"

    def test_card_has_required_fields(self):
        card_path = Path(__file__).parent.parent / "agent_card.json"
        card = json.loads(card_path.read_text())
        for field in ("name", "description", "version", "url", "capabilities", "skills"):
            assert field in card, f"Missing field: {field}"


# --- A2A Server endpoints ---

class TestA2AServerEndpoints:
    @pytest.fixture
    def client(self):
        from agents.web_research.main import build_app
        app = build_app()
        return TestClient(app)

    def test_agent_card_endpoint(self, client):
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "web-research-agent"
        assert "skills" in data

    def test_rpc_endpoint_exists(self, client):
        # The A2A JSON-RPC endpoint should return 4xx for malformed requests, not 404
        response = client.post("/", json={})
        assert response.status_code != 404


# --- AgentExecutor ---

class TestWebResearchAgentExecutor:
    @pytest.mark.asyncio
    async def test_execute_calls_run_web_research(self):
        from agents.web_research.main import WebResearchAgentExecutor
        from a2a.server.events import EventQueue
        from a2a.utils import new_agent_text_message

        executor = WebResearchAgentExecutor()

        mock_context = MagicMock()
        mock_context.current_task = None
        mock_part = MagicMock()
        mock_part.root.text = "What is RAG?"
        mock_context.message.parts = [mock_part]

        mock_queue = AsyncMock()

        with patch("agents.web_research.main.run_web_research", new_callable=AsyncMock) as mock_run, \
             patch("agents.web_research.main.new_task") as mock_new_task, \
             patch("agents.web_research.main.TaskUpdater") as MockUpdater:

            mock_task = MagicMock()
            mock_task.id = "task-1"
            mock_task.context_id = "ctx-1"
            mock_new_task.return_value = mock_task
            mock_run.return_value = "Research result"

            mock_updater = AsyncMock()
            MockUpdater.return_value = mock_updater

            await executor.execute(mock_context, mock_queue)

        mock_run.assert_awaited_once_with("What is RAG?")

    @pytest.mark.asyncio
    async def test_execute_handles_empty_query(self):
        from agents.web_research.main import WebResearchAgentExecutor

        executor = WebResearchAgentExecutor()

        mock_context = MagicMock()
        mock_context.current_task = None
        mock_context.message.parts = []
        mock_queue = AsyncMock()

        with patch("agents.web_research.main.new_task") as mock_new_task, \
             patch("agents.web_research.main.TaskUpdater") as MockUpdater:

            mock_task = MagicMock()
            mock_task.id = "task-1"
            mock_task.context_id = "ctx-1"
            mock_new_task.return_value = mock_task

            mock_updater = AsyncMock()
            MockUpdater.return_value = mock_updater

            await executor.execute(mock_context, mock_queue)

        # failed() should have been called
        mock_updater.failed.assert_awaited_once()
