"""Unit tests for the ADK coordinator (coordinator.py) and orchestrator main.py."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")


# --- Coordinator build ---

class TestBuildCoordinator:
    def test_coordinator_builds(self):
        from orchestrator.coordinator import build_coordinator
        from orchestrator.config import OrchestratorConfig
        config = OrchestratorConfig.from_env()
        coordinator = build_coordinator(config)
        assert coordinator is not None

    def test_coordinator_name(self):
        from orchestrator.coordinator import build_coordinator
        from orchestrator.config import OrchestratorConfig
        config = OrchestratorConfig.from_env()
        coordinator = build_coordinator(config)
        assert coordinator.name == "research_coordinator"

    def test_coordinator_has_three_sub_agents(self):
        from orchestrator.coordinator import build_coordinator
        from orchestrator.config import OrchestratorConfig
        config = OrchestratorConfig.from_env()
        coordinator = build_coordinator(config)
        assert len(coordinator.sub_agents) == 3

    def test_coordinator_sub_agent_names(self):
        from orchestrator.coordinator import build_coordinator
        from orchestrator.config import OrchestratorConfig
        config = OrchestratorConfig.from_env()
        coordinator = build_coordinator(config)
        names = {a.name for a in coordinator.sub_agents}
        assert names == {"web_research", "rag_lookup", "summariser"}


# --- POST /research endpoint ---

class TestResearchEndpoint:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from orchestrator.main import app
        return TestClient(app)

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_empty_query_returns_400(self, client):
        response = client.post("/research", json={"query": "  "})
        assert response.status_code == 400

    def test_research_returns_valid_shape(self, client):
        """Mock the runner so we don't hit real LLM/A2A services."""
        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.author = "research_coordinator"
        mock_event.content = MagicMock()
        mock_event.content.parts = [MagicMock(text="Test answer")]

        async def _fake_run_async(**kwargs):
            yield mock_event

        mock_runner = MagicMock()
        mock_runner.run_async = _fake_run_async

        mock_session_service = MagicMock()
        mock_session_service.create_session = AsyncMock()

        mock_config = MagicMock()
        mock_config.a2a_timeout = 30.0

        with patch("orchestrator.main._get_runner", return_value=mock_runner), \
             patch("orchestrator.main._session_service", mock_session_service), \
             patch("orchestrator.main._config", mock_config):
            response = client.post("/research", json={"query": "What is RAG?"})

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert "route" in data
        assert "retrieved_context" in data

    def test_runner_exception_returns_500(self, client):
        async def _fake_run_async(**kwargs):
            raise RuntimeError("boom")
            yield  # make it an async generator

        mock_runner = MagicMock()
        mock_runner.run_async = _fake_run_async

        mock_session_service = MagicMock()
        mock_session_service.create_session = AsyncMock()

        mock_config = MagicMock()
        mock_config.a2a_timeout = 30.0

        with patch("orchestrator.main._get_runner", return_value=mock_runner), \
             patch("orchestrator.main._session_service", mock_session_service), \
             patch("orchestrator.main._config", mock_config):
            response = client.post("/research", json={"query": "trigger error"})

        assert response.status_code == 500
        assert response.json()["detail"] == "Internal research error"

    def test_timeout_returns_504(self, client):
        import asyncio

        async def _slow_run_async(**kwargs):
            await asyncio.sleep(10)
            yield  # never reached

        mock_runner = MagicMock()
        mock_runner.run_async = _slow_run_async

        mock_session_service = MagicMock()
        mock_session_service.create_session = AsyncMock()

        mock_config = MagicMock()
        mock_config.a2a_timeout = 0.05  # 50ms — triggers timeout immediately

        with patch("orchestrator.main._get_runner", return_value=mock_runner), \
             patch("orchestrator.main._session_service", mock_session_service), \
             patch("orchestrator.main._config", mock_config):
            response = client.post("/research", json={"query": "slow query"})

        assert response.status_code == 504
        assert response.json()["detail"] == "Research timed out"
