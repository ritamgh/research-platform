"""FastAPI app for the research orchestrator — exposes POST /research."""
import logging
import os
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from google.adk.runners import InMemorySessionService, Runner
from google.genai import types
from pydantic import BaseModel

from orchestrator.config import OrchestratorConfig
from orchestrator.coordinator import build_coordinator

logger = logging.getLogger(__name__)

_runner: Runner | None = None
_session_service: InMemorySessionService | None = None
_config: OrchestratorConfig | None = None

_APP_NAME = "research-platform"


def _get_runner() -> Runner:
    global _runner, _session_service, _config
    if _runner is None:
        _config = OrchestratorConfig.from_env()
        coordinator = build_coordinator(_config)
        _session_service = InMemorySessionService()
        _runner = Runner(
            app_name=_APP_NAME,
            agent=coordinator,
            session_service=_session_service,
        )
    return _runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault(
            "LANGCHAIN_PROJECT",
            os.environ.get("LANGSMITH_PROJECT", "research-platform"),
        )
    yield


app = FastAPI(title="Research Orchestrator", version="2.0.0", lifespan=lifespan)


class ResearchRequest(BaseModel):
    query: str


class ResearchResponse(BaseModel):
    answer: str
    sources: list[str]
    route: str
    retrieved_context: list[str]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        runner = _get_runner()
        user_id = "research-user"
        session_id = str(uuid.uuid4())

        await _session_service.create_session(
            app_name=_APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=request.query)],
        )

        final_answer = ""
        retrieved_context: list[str] = []

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_answer = event.content.parts[0].text or ""
            # Collect sub-agent responses for eval pipeline
            if (
                event.author != "research_coordinator"
                and event.author != "user"
                and event.content
                and event.content.parts
            ):
                for part in event.content.parts:
                    if part.text:
                        retrieved_context.append(part.text)

        return ResearchResponse(
            answer=final_answer,
            sources=[],
            route="adk",
            retrieved_context=retrieved_context,
        )
    except Exception as exc:
        logger.exception("Orchestrator failed")
        raise HTTPException(status_code=500, detail="Internal research error") from exc


if __name__ == "__main__":
    port = int(os.environ.get("ORCHESTRATOR_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
