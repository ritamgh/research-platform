"""FastAPI app for the research orchestrator — exposes POST /research."""
import asyncio
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager

import tempfile

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client as McpClient
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class ResearchRequest(BaseModel):
    query: str


class ResearchResponse(BaseModel):
    answer: str
    sources: list[str]
    route: str
    retrieved_context: list[str]


_VECTOR_DB_MCP_URL = os.environ.get("VECTOR_DB_MCP_URL", "http://localhost:9002/mcp")
_FILE_READER_MCP_URL = os.environ.get("FILE_READER_MCP_URL", "http://localhost:9003/mcp")


async def _call_vector_db(tool: str, args: dict) -> dict:
    async with McpClient(_VECTOR_DB_MCP_URL) as client:
        result = await client.call_tool(tool, args)
        return json.loads(result.content[0].text)


@app.get("/health")
def health():
    return {"status": "ok"}


class IngestRequest(BaseModel):
    title: str
    content: str
    url: str
    collection: str = "documents"


@app.get("/corpus")
async def list_corpus(collection: str = "documents"):
    try:
        return await _call_vector_db("list_documents", {"collection": collection})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vector DB error: {exc}") from exc


@app.post("/corpus")
async def ingest_document(req: IngestRequest):
    try:
        return await _call_vector_db("ingest_document", {
            "title": req.title,
            "content": req.content,
            "url": req.url,
            "collection": req.collection,
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vector DB error: {exc}") from exc


@app.post("/corpus/upload")
async def extract_file_text(file: UploadFile):
    """Accept a file upload and return extracted text via the file_reader MCP tool."""
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in (".pdf", ".txt", ".md"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    data = await file.read()
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            async with McpClient(_FILE_READER_MCP_URL) as client:
                result = await client.call_tool("read_file", {"source": tmp_path})
            payload = json.loads(result.content[0].text)
            return {"text": payload["text"]}
        finally:
            os.unlink(tmp_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"File reader error: {exc}") from exc


_URL_RE = re.compile(r'https?://[^\s\)\]\'"<>,]+')
_RAG_SOURCES_RE = re.compile(r'<rag_sources>(.*?)</rag_sources>', re.DOTALL)


def _extract_sources(texts: list[str]) -> list[str]:
    """Extract unique sources from text chunks.

    Picks up items in <rag_sources> tags (from RAG agent) and https?:// URLs.
    """
    seen: set[str] = set()
    sources: list[str] = []

    def _add(s: str) -> None:
        s = s.strip().rstrip('.')
        if s and s not in seen:
            seen.add(s)
            sources.append(s)

    for text in texts:
        for match in _RAG_SOURCES_RE.finditer(text):
            for item in match.group(1).split('|'):
                _add(item)
        for url in _URL_RE.findall(text):
            _add(url)

    return sources


_SUB_AGENT_AUTHORS = {"rag_lookup", "web_research", "summariser"}


async def _collect_events(
    runner: Runner,
    user_id: str,
    session_id: str,
    message: types.Content,
) -> tuple[str, list[str], list[str]]:
    """Consume ADK runner events and return (final_answer, retrieved_context, sub_agent_texts)."""
    final_answer = ""
    retrieved_context: list[str] = []
    sub_agent_texts: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        logger.debug(
            "Event author=%s is_final=%s has_content=%s",
            event.author,
            event.is_final_response(),
            bool(event.content),
        )
        if event.is_final_response():
            if event.content and event.content.parts:
                final_answer = event.content.parts[0].text or ""

        if event.author in _SUB_AGENT_AUTHORS and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    sub_agent_texts.append(part.text)
                    if not event.is_final_response():
                        retrieved_context.append(part.text)

    return final_answer, retrieved_context, sub_agent_texts


@app.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    session_id = str(uuid.uuid4())
    try:
        runner = _get_runner()
        # Use session_id as user_id so each request is fully isolated
        user_id = session_id

        await _session_service.create_session(
            app_name=_APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        logger.info("Research request started session=%s query=%r", session_id, request.query[:80])

        message = types.Content(
            role="user",
            parts=[types.Part(text=request.query)],
        )

        try:
            final_answer, retrieved_context, sub_agent_texts = await asyncio.wait_for(
                _collect_events(runner, user_id, session_id, message),
                timeout=_config.a2a_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Research timed out session=%s after %.1fs", session_id, _config.a2a_timeout)
            raise HTTPException(status_code=504, detail="Research timed out")

        sources = _extract_sources(sub_agent_texts + [final_answer])
        # Strip metadata markers from the final answer before showing to the user.
        final_answer = re.sub(r'\[CONFIDENCE:[^\]]+\]\s*', '', final_answer)
        final_answer = _RAG_SOURCES_RE.sub('', final_answer)
        final_answer = re.sub(r'\n\nSources:\n(?:- https?://\S+\n?)+', '', final_answer).rstrip()
        logger.info(
            "Research request completed session=%s context_chunks=%d sources=%d",
            session_id, len(retrieved_context), len(sources),
        )
        return ResearchResponse(
            answer=final_answer,
            sources=sources,
            route="adk",
            retrieved_context=retrieved_context,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Orchestrator failed session=%s", session_id)
        raise HTTPException(status_code=500, detail="Internal research error") from exc
    finally:
        # Clean up session to prevent memory accumulation
        try:
            await _session_service.delete_session(
                app_name=_APP_NAME,
                user_id=session_id,
                session_id=session_id,
            )
        except Exception:
            pass  # Best-effort cleanup — don't fail the response


if __name__ == "__main__":
    port = int(os.environ.get("ORCHESTRATOR_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
