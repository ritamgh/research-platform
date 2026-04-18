"""ADK coordinator: builds a multi-agent research coordinator."""
import warnings

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.models.lite_llm import LiteLlm

from orchestrator.config import OrchestratorConfig

# Suppress experimental warnings from RemoteA2aAgent / to_a2a
warnings.filterwarnings("ignore", category=UserWarning, module="google.adk")

COORDINATOR_INSTRUCTION = """You are a research coordinator. For EVERY query, follow these steps in order:

STEP 1 — Always delegate to rag_lookup first, no exceptions.

STEP 2 — Read the confidence marker at the start of rag_lookup's response:
  - [CONFIDENCE: HIGH]   → answer directly from the RAG result, do not do web search.
  - [CONFIDENCE: MEDIUM] → also delegate to web_research, then combine both using the summariser.
  - [CONFIDENCE: LOW]    → also delegate to web_research, then combine both using the summariser.

STEP 3 — When delegating to the summariser, use EXACTLY this format:

QUERY: <the original question>
WEB_FINDINGS: <full text returned by web_research>
RAG_FINDINGS: <full text returned by rag_lookup>

- If rag_lookup errors, fall back to web_research only.
- If the query is a simple factual question (math, definitions) that needs no research: answer directly.
- Always strip the [CONFIDENCE: ...] marker before showing the final answer to the user.
- Always return a clear, cited answer. Do not ask clarifying questions.
"""


def build_coordinator(config: OrchestratorConfig) -> Agent:
    """Build the ADK research coordinator with remote sub-agents."""
    web_research = RemoteA2aAgent(
        name="web_research",
        description="Searches the web for recent information on a given topic.",
        agent_card=f"{config.web_research_url}/.well-known/agent-card.json",
    )
    rag_lookup = RemoteA2aAgent(
        name="rag_lookup",
        description="Searches the local document corpus for information on a given topic.",
        agent_card=f"{config.rag_url}/.well-known/agent-card.json",
    )
    summariser = RemoteA2aAgent(
        name="summariser",
        description="Synthesises web and RAG findings into a concise cited answer.",
        agent_card=f"{config.summariser_url}/.well-known/agent-card.json",
    )
    return Agent(
        name="research_coordinator",
        model=LiteLlm(model=f"openai/{config.router_model}"),
        instruction=COORDINATOR_INSTRUCTION,
        description="Coordinates web research, RAG lookup, and summarisation to answer research queries.",
        sub_agents=[web_research, rag_lookup, summariser],
    )
