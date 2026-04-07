"""ADK coordinator: builds a multi-agent research coordinator."""
import warnings

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.models.lite_llm import LiteLlm

from orchestrator.config import OrchestratorConfig

# Suppress experimental warnings from RemoteA2aAgent / to_a2a
warnings.filterwarnings("ignore", category=UserWarning, module="google.adk")

COORDINATOR_INSTRUCTION = """You are a research coordinator. Given a research query, decide how to route it:

- If the query asks about recent events, current news, or needs up-to-date information: delegate to web_research.
- If the query is about internal documents, stored corpus, or specific organisational knowledge: delegate to rag_lookup.
- If the query needs both web and corpus information: delegate to web_research first, then rag_lookup, then synthesise with summariser. Pass the query and findings as named arguments: query, web_findings, rag_findings.
- If the query is a simple factual question (math, definitions) that needs no research: answer directly.

Always return a clear, cited answer to the user. Do not ask clarifying questions — do your best with the query as given.
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
