"""FastAPI app for the research orchestrator — exposes POST /research."""
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from orchestrator.graph import build_graph

logger = logging.getLogger(__name__)

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure LangSmith tracing if credentials are present
    if os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault(
            "LANGCHAIN_PROJECT",
            os.environ.get("LANGSMITH_PROJECT", "research-platform"),
        )
    yield


app = FastAPI(title="Research Orchestrator", version="1.0.0", lifespan=lifespan)


class ResearchRequest(BaseModel):
    query: str


class ResearchResponse(BaseModel):
    answer: str
    sources: list[str]
    route: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        result = await _get_graph().ainvoke({"query": request.query})
        return ResearchResponse(
            answer=result.get("final_answer", ""),
            sources=result.get("sources", []),
            route=result.get("route", "unknown"),
        )
    except Exception as exc:
        logger.exception("Orchestrator graph failed")
        raise HTTPException(status_code=500, detail="Internal research error") from exc


if __name__ == "__main__":
    port = int(os.environ.get("ORCHESTRATOR_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
