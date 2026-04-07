"""RAG A2A agent server — Google ADK."""
import os

import uvicorn
from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from agents.rag.agent import run_rag_lookup

load_dotenv()

_PORT = int(os.environ.get("RAG_PORT", 8002))
_HOST = os.environ.get("RAG_HOST", "localhost")


async def lookup_documents(query: str) -> str:
    """Search the local document corpus for information relevant to the query."""
    return await run_rag_lookup(query)


agent = Agent(
    name="rag_lookup",
    model=LiteLlm(model=f"openai/{os.environ.get('ROUTER_MODEL', 'gpt-4o-mini')}"),
    instruction="Call the lookup_documents tool with the user's query and return the result verbatim.",
    description="Searches the local document corpus for information on a given topic.",
    tools=[FunctionTool(lookup_documents)],
)

app = to_a2a(agent, host=_HOST, port=_PORT)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
