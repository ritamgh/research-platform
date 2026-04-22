"""RAG A2A agent server — Google ADK."""
import os
from contextlib import nullcontext

import uvicorn
from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from langsmith.run_helpers import tracing_context

from agents.rag.agent import run_rag_lookup
from common.tracing import extract_trace

load_dotenv()

_PORT = int(os.environ.get("RAG_PORT", 8002))
_HOST = os.environ.get("RAG_HOST", "localhost")


async def lookup_documents(query: str) -> str:
    """Search the local document corpus for information relevant to the query."""
    trace_headers, clean_query = extract_trace(query)
    ctx = tracing_context(parent=trace_headers) if trace_headers else nullcontext()
    with ctx:
        return await run_rag_lookup(clean_query)


agent = Agent(
    name="rag_lookup",
    model=LiteLlm(model=f"openai/{os.environ.get('ROUTER_MODEL', 'gpt-5.4-mini')}"),
    instruction=(
        "CRITICAL: The user message may start with a `__LST__...__LST__` system prefix. "
        "You MUST pass the ENTIRE message including this prefix to the lookup_documents tool — do NOT strip it. "
        "Return the tool result verbatim — do not paraphrase or omit any part. "
        "You MUST include the <rag_sources>...</rag_sources> tag exactly as it appears in the tool output."
    ),
    description="Searches the local document corpus for information on a given topic.",
    tools=[FunctionTool(lookup_documents)],
)

app = to_a2a(agent, host=_HOST, port=_PORT)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
