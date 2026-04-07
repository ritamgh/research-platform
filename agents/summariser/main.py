"""Summariser A2A agent server — Google ADK."""
import os

import uvicorn
from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from agents.summariser.agent import run_summariser

load_dotenv()

_PORT = int(os.environ.get("SUMMARISER_PORT", 8003))
_HOST = os.environ.get("SUMMARISER_HOST", "localhost")


async def synthesise_findings(
    query: str,
    web_findings: str = "",
    rag_findings: str = "",
) -> str:
    """Synthesise web and RAG findings into a final cited answer.

    Args:
        query: The original research question.
        web_findings: Raw text from the web research agent (may be empty).
        rag_findings: Raw text from the RAG lookup agent (may be empty).
    """
    return await run_summariser(
        query=query,
        web_findings=web_findings,
        rag_findings=rag_findings,
    )


agent = Agent(
    name="summariser",
    model=LiteLlm(model=f"openai/{os.environ.get('ROUTER_MODEL', 'gpt-4o-mini')}"),
    instruction=(
        "Call the synthesise_findings tool with the query and any available findings, "
        "then return the result verbatim."
    ),
    description="Synthesises web and RAG findings into a concise cited answer.",
    tools=[FunctionTool(synthesise_findings)],
)

app = to_a2a(agent, host=_HOST, port=_PORT)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
