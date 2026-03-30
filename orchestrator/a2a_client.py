"""Async A2A client for calling A2A agent servers."""
import uuid

import httpx
from a2a.client import A2ACardResolver, A2AClient, create_text_message_object
from a2a.types import AgentCard, MessageSendParams, SendMessageRequest, Task


class A2ACallError(Exception):
    """Raised when an A2A agent call fails."""


async def call_agent(agent_url: str, query: str, timeout: float = 30.0) -> str:
    """Send a text query to an A2A agent and return the artifact text.

    Args:
        agent_url: Base URL of the agent (e.g. http://localhost:8001)
        query: The text query to send
        timeout: HTTP timeout in seconds

    Returns:
        The text content of the first artifact from the agent's response

    Raises:
        A2ACallError: If the call fails, times out, or returns an error
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            client = A2AClient(httpx_client=http, url=agent_url)
            message = create_text_message_object(content=query)
            request = SendMessageRequest(
                id=str(uuid.uuid4()),
                params=MessageSendParams(message=message),
            )
            response = await client.send_message(request)
    except httpx.TimeoutException as exc:
        raise A2ACallError(f"Timeout calling {agent_url}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise A2ACallError(f"HTTP error calling {agent_url}: {exc}") from exc

    # Check for JSON-RPC error
    if hasattr(response.root, "error"):
        raise A2ACallError(f"Agent error from {agent_url}: {response.root.error}")

    # Extract text from the result
    result = response.root.result
    if isinstance(result, Task):
        artifacts = result.artifacts or []
        for artifact in artifacts:
            for part in artifact.parts:
                if hasattr(part.root, "text"):
                    return part.root.text
        raise A2ACallError(f"No text artifact in Task response from {agent_url}")
    else:
        # Message response
        for part in result.parts:
            if hasattr(part.root, "text"):
                return part.root.text
        raise A2ACallError(f"No text part in Message response from {agent_url}")


async def discover_agent(agent_url: str, timeout: float = 10.0) -> AgentCard:
    """Fetch and return the agent card from /.well-known/agent.json.

    Args:
        agent_url: Base URL of the agent
        timeout: HTTP timeout in seconds

    Returns:
        Parsed AgentCard

    Raises:
        A2ACallError: If discovery fails
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            resolver = A2ACardResolver(httpx_client=http, base_url=agent_url)
            return await resolver.get_agent_card()
    except httpx.TimeoutException as exc:
        raise A2ACallError(f"Timeout discovering {agent_url}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise A2ACallError(f"HTTP error discovering {agent_url}: {exc}") from exc
