"""ADK coordinator: builds a multi-agent research coordinator."""
import warnings

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.models.lite_llm import LiteLlm

from orchestrator.config import OrchestratorConfig

# Suppress experimental warnings from RemoteA2aAgent / to_a2a
warnings.filterwarnings("ignore", category=UserWarning, module="google.adk")

COORDINATOR_INSTRUCTION = """You are a research coordinator handling the default confidence-gated path.

CRITICAL — PREFIX PRESERVATION:
The user message starts with a system prefix that looks like `__LST__` followed by a long string of letters/numbers/symbols ending with another `__LST__`. You MUST include this entire prefix VERBATIM at the very start of every message you send to any sub-agent (rag_lookup, web_research, summariser). Do NOT drop, modify, or paraphrase this prefix — copy it character-for-character.

STEP 1 — Delegate to rag_lookup. Include the full `__LST__...__LST__` prefix + the user's query.

STEP 2 — Inspect rag_lookup's response for a [CONFIDENCE: ...] marker:
  - [CONFIDENCE: HIGH]   → Return the RAG answer directly. STOP. Do NOT call web_research or summariser.
  - [CONFIDENCE: MEDIUM] → You MUST now call web_research (include prefix + original query), then call summariser.
  - [CONFIDENCE: LOW]    → You MUST now call web_research (include prefix + original query), then call summariser.

For MEDIUM and LOW confidence, calling web_research is MANDATORY — never skip it.

When calling the summariser, include the prefix and use EXACTLY this format:
QUERY: <original question>
WEB_FINDINGS: <web_research result>
RAG_FINDINGS: <rag_lookup result>

Rules:
- Strip [CONFIDENCE: ...] from the final answer.
- If rag_lookup errors, fall back to web_research only.
- Never ask clarifying questions. Always return a cited answer.
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
