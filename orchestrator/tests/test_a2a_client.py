"""Unit tests for orchestrator.a2a_client using respx to mock httpx."""
import pytest
import httpx
import respx
from unittest.mock import AsyncMock, patch

from orchestrator.a2a_client import A2ACallError, call_agent, discover_agent

AGENT_URL = "http://localhost:8001"

_SUCCESS_TASK_RESPONSE = {
    "jsonrpc": "2.0",
    "id": "test-id",
    "result": {
        "id": "task-1",
        "contextId": "ctx-1",
        "kind": "task",
        "status": {"state": "completed"},
        "artifacts": [
            {
                "artifactId": "art-1",
                "parts": [{"kind": "text", "text": "the result text"}],
            }
        ],
    },
}

_SUCCESS_MESSAGE_RESPONSE = {
    "jsonrpc": "2.0",
    "id": "test-id",
    "result": {
        "kind": "message",
        "messageId": "msg-1",
        "contextId": "ctx-1",
        "role": "agent",
        "parts": [{"kind": "text", "text": "message result text"}],
    },
}

_ERROR_RESPONSE = {
    "jsonrpc": "2.0",
    "id": "test-id",
    "error": {"code": -32603, "message": "internal server error"},
}

# The A2A SDK default card path is agent-card.json, not agent.json
_AGENT_CARD_URL = f"{AGENT_URL}/.well-known/agent-card.json"


class TestCallAgent:
    @pytest.mark.asyncio
    async def test_returns_text_from_task_artifact(self):
        with respx.mock:
            respx.post(AGENT_URL).mock(
                return_value=httpx.Response(200, json=_SUCCESS_TASK_RESPONSE)
            )
            result = await call_agent(AGENT_URL, "test query")
        assert result == "the result text"

    @pytest.mark.asyncio
    async def test_returns_text_from_message_parts(self):
        with respx.mock:
            respx.post(AGENT_URL).mock(
                return_value=httpx.Response(200, json=_SUCCESS_MESSAGE_RESPONSE)
            )
            result = await call_agent(AGENT_URL, "test query")
        assert result == "message result text"

    @pytest.mark.asyncio
    async def test_raises_a2a_call_error_on_timeout(self):
        # The A2A SDK transport wraps httpx.TimeoutException into A2AClientTimeoutError,
        # which is NOT a subclass of httpx.TimeoutException. We mock at the send_message
        # level to simulate the httpx timeout reaching call_agent's except clause.
        with patch("orchestrator.a2a_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("orchestrator.a2a_client.A2AClient") as MockA2AClient:
                mock_a2a = AsyncMock()
                mock_a2a.send_message = AsyncMock(
                    side_effect=httpx.TimeoutException("connection timed out")
                )
                MockA2AClient.return_value = mock_a2a

                with pytest.raises(A2ACallError, match="Timeout"):
                    await call_agent(AGENT_URL, "test query", timeout=5.0)

    @pytest.mark.asyncio
    async def test_raises_a2a_call_error_on_non_200_status(self):
        # The A2A SDK transport wraps HTTPStatusError into A2AClientHTTPError.
        # Mock at the A2AClient.send_message level with an httpx.HTTPError.
        with patch("orchestrator.a2a_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("orchestrator.a2a_client.A2AClient") as MockA2AClient:
                mock_a2a = AsyncMock()
                mock_a2a.send_message = AsyncMock(
                    side_effect=httpx.HTTPError("500 Internal Server Error")
                )
                MockA2AClient.return_value = mock_a2a

                with pytest.raises(A2ACallError):
                    await call_agent(AGENT_URL, "test query")

    @pytest.mark.asyncio
    async def test_raises_a2a_call_error_when_response_has_error_field(self):
        with respx.mock:
            respx.post(AGENT_URL).mock(
                return_value=httpx.Response(200, json=_ERROR_RESPONSE)
            )
            with pytest.raises(A2ACallError, match="Agent error"):
                await call_agent(AGENT_URL, "test query")


class TestDiscoverAgent:
    @pytest.mark.asyncio
    async def test_raises_a2a_call_error_on_timeout(self):
        # The A2A SDK card resolver wraps httpx.TimeoutException (a RequestError subclass)
        # into A2AClientHTTPError before discover_agent's except clause sees it.
        # discover_agent catches this via the broad `except Exception` branch and re-raises
        # as A2ACallError with "Failed to parse agent card" prefix.
        with respx.mock:
            respx.get(_AGENT_CARD_URL).mock(
                side_effect=httpx.TimeoutException("discovery timed out")
            )
            with pytest.raises(A2ACallError, match="Failed to parse agent card"):
                await discover_agent(AGENT_URL, timeout=5.0)
