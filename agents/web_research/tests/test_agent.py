"""Unit tests for the web_research agent."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.web_research.agent import run_web_research, build_search_tool


MOCK_SEARCH_RESULT = json.dumps([
    {
        "title": "Mechanistic Interpretability Overview",
        "url": "https://example.com/mi",
        "snippet": "Mechanistic interpretability studies neural network internals...",
    }
])


# --- mcp_client ---

class TestMcpClient:
    def test_module_imports(self):
        from agents.web_research import mcp_client
        assert callable(mcp_client.search_web)

    def test_default_url_env(self, monkeypatch):
        monkeypatch.setenv("WEB_SEARCH_MCP_URL", "http://localhost:9001")
        import importlib
        import agents.web_research.mcp_client as mod
        importlib.reload(mod)
        assert mod.WEB_SEARCH_MCP_URL == "http://localhost:9001"


# --- build_search_tool ---

class TestBuildSearchTool:
    def test_returns_runnable_tool(self):
        async def mock_search(query, num_results=5):
            return MOCK_SEARCH_RESULT

        tool = build_search_tool(search_fn=mock_search)
        # CrewAI Tool wraps the function; it exposes .run() not __call__
        assert hasattr(tool, "run")
        assert hasattr(tool, "name")

    def test_tool_name(self):
        async def mock_search(query, num_results=5):
            return MOCK_SEARCH_RESULT

        tool = build_search_tool(search_fn=mock_search)
        assert tool.name == "web_search"

    def test_tool_calls_search_fn(self):
        calls = []

        async def mock_search(query, num_results=5):
            calls.append(query)
            return MOCK_SEARCH_RESULT

        tool = build_search_tool(search_fn=mock_search)
        result = tool.run("LLM interpretability")
        assert "LLM interpretability" in calls
        assert MOCK_SEARCH_RESULT in result


# --- run_web_research ---

class TestRunWebResearch:
    @pytest.mark.asyncio
    async def test_returns_string(self):
        async def mock_search(query, num_results=5):
            return MOCK_SEARCH_RESULT

        with patch("agents.web_research.agent.Crew") as MockCrew, \
             patch("agents.web_research.agent.Agent"), \
             patch("agents.web_research.agent.Task"):
            mock_crew_instance = MagicMock()
            mock_crew_instance.kickoff.return_value = "Research findings about LLMs"
            MockCrew.return_value = mock_crew_instance

            result = await run_web_research(
                "What is mechanistic interpretability?", search_fn=mock_search
            )

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_passes_query_to_task(self):
        async def mock_search(query, num_results=5):
            return MOCK_SEARCH_RESULT

        with patch("agents.web_research.agent.Crew") as MockCrew, \
             patch("agents.web_research.agent.Agent"), \
             patch("agents.web_research.agent.Task") as MockTask:

            mock_crew_instance = MagicMock()
            mock_crew_instance.kickoff.return_value = "Some result"
            MockCrew.return_value = mock_crew_instance

            query = "What are sparse autoencoders?"
            await run_web_research(query, search_fn=mock_search)

            call_kwargs = MockTask.call_args
            assert query in call_kwargs.kwargs["description"]
