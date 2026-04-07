"""Web research A2A agent server — Google ADK."""
import os

import uvicorn
from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from agents.web_research.agent import run_web_research

load_dotenv()

_PORT = int(os.environ.get("WEB_RESEARCH_PORT", 8001))
_HOST = os.environ.get("WEB_RESEARCH_HOST", "localhost")


async def search_web(query: str) -> str:
    """Search the web for recent information about the given query."""
    return await run_web_research(query)


agent = Agent(
    name="web_research",
    model=LiteLlm(model=f"openai/{os.environ.get('ROUTER_MODEL', 'gpt-4o-mini')}"),
    instruction="Call the search_web tool with the user's query and return the result verbatim.",
    description="Searches the web for recent information on a given topic.",
    tools=[FunctionTool(search_web)],
)

app = to_a2a(agent, host=_HOST, port=_PORT)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
