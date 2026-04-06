"""Orchestrator configuration loaded from environment variables."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class OrchestratorConfig:
    web_research_url: str
    rag_url: str
    summariser_url: str
    a2a_timeout: float
    router_model: str
    langsmith_project: str

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        return cls(
            web_research_url=os.environ.get(
                "WEB_RESEARCH_AGENT_URL", "http://localhost:8001"
            ),
            rag_url=os.environ.get("RAG_AGENT_URL", "http://localhost:8002"),
            summariser_url=os.environ.get(
                "SUMMARISER_AGENT_URL", "http://localhost:8003"
            ),
            a2a_timeout=float(os.environ.get("A2A_TIMEOUT", "30.0")),
            router_model=os.environ.get(
                "ROUTER_MODEL", "gpt-4o-mini"
            ),
            langsmith_project=os.environ.get(
                "LANGSMITH_PROJECT", "research-platform"
            ),
        )
