"""FastAPI app for the research orchestrator — exposes POST /research."""
import asyncio
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager

import tempfile

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client as McpClient
from google.adk.runners import InMemorySessionService, Runner
from google.genai import types
from langsmith import traceable
from pydantic import BaseModel

from common.tracing import get_trace_headers, inject_trace, extract_trace
from orchestrator.config import OrchestratorConfig
from orchestrator.coordinator import build_coordinator

logger = logging.getLogger(__name__)

_runner: Runner | None = None
_session_service: InMemorySessionService | None = None
_config: OrchestratorConfig | None = None

_APP_NAME = "research-platform"


def _get_config() -> OrchestratorConfig:
    global _config
    if _config is None:
        _config = OrchestratorConfig.from_env()
    return _config


def _get_runner() -> Runner:
    global _runner, _session_service
    if _runner is None:
        config = _get_config()
        coordinator = build_coordinator(config)
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
            os.environ.get("LANGSMITH_PROJECT", "research-app"),
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
_RAG_SOURCES_RE = re.compile(r'<rag_sources(?:[^>]*)>(.*?)</rag_sources>', re.DOTALL)
_RAG_SOURCES_FULL_RE = re.compile(r'<rag_sources[^>]*>.*?</rag_sources>', re.DOTALL)
_RAG_CONFIDENCE_ATTR_RE = re.compile(r'<rag_sources[^>]*\bconfidence="(HIGH|MEDIUM|LOW)"')


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

_CONFIDENCE_RE = re.compile(r'\[CONFIDENCE:\s*(HIGH|MEDIUM|LOW)\]')

# Keyword patterns for deterministic pre-routing (avoids relying on LLM to parse intent)
_WEB_ONLY_RE = re.compile(
    r'^\s*(google|search the web for|search for|look up online|what does the internet say about)\b',
    re.IGNORECASE,
)
_WEB_THEN_RAG_RE = re.compile(
    r'(google|search the web|search online|look up online).{0,80}'
    r'(then|and then|and also)\s.{0,40}(local|database|corpus|document|my)',
    re.IGNORECASE,
)
_RAG_THEN_WEB_RE = re.compile(
    r'(search the web|google|look up online|search online).{0,40}(about them|about those|to clarify|to explain|them\b)|'
    r'(find|get|look).{0,80}(internship|corpus|document|local|my).{0,120}'
    r'then.{0,60}(google|search the web|look up online)',
    re.IGNORECASE,
)


def _detect_route_directive(query: str) -> str:
    """Return an explicit routing directive to prepend to the coordinator message."""
    if _WEB_THEN_RAG_RE.search(query):
        return "[ROUTING: WEB_THEN_RAG] "
    if _RAG_THEN_WEB_RE.search(query):
        return "[ROUTING: RAG_THEN_WEB] "
    if _WEB_ONLY_RE.search(query):
        return "[ROUTING: WEB_ONLY] "
    return ""


async def _call_a2a(
    agent_url: str, query: str, timeout: float = 30.0, *, trace_headers: dict | None = None,
) -> str:
    """Call an A2A agent directly via JSONRPC, bypassing the ADK coordinator."""
    msg_id = str(uuid.uuid4())
    marked_query = inject_trace(query, trace_headers) if trace_headers else query
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": msg_id,
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": marked_query}],
                "messageId": msg_id,
            }
        },
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(agent_url, json=payload)
        resp.raise_for_status()
    data = resp.json()
    # Extract text from A2A artifacts or message parts
    result = data.get("result", {})
    for artifact in result.get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("text"):
                return _unwrap_a2a(part["text"])
    for part in result.get("message", {}).get("parts", []):
        if part.get("text"):
            return _unwrap_a2a(part["text"])
    return ""


async def _call_a2a_safe(
    agent_url: str, query: str, timeout: float = 30.0, *, trace_headers: dict | None = None,
) -> str:
    """Call an A2A agent, returning empty string on failure instead of raising."""
    try:
        return await _call_a2a(agent_url, query, timeout, trace_headers=trace_headers)
    except Exception as exc:
        logger.warning("A2A call to %s failed: %s", agent_url, exc)
        return ""


async def _run_research_direct(
    query: str,
    directive: str,
    timeout: float,
    *,
    trace_headers: dict | None = None,
) -> dict:
    """Execute explicit routing (RAG_THEN_WEB / WEB_THEN_RAG / WEB_ONLY) via direct A2A calls."""
    config = _config
    rag_url = config.rag_url
    web_url = config.web_research_url
    sum_url = config.summariser_url

    rag_result = web_result = ""

    if directive == "RAG_THEN_WEB":
        rag_result = await _call_a2a(rag_url, query, timeout, trace_headers=trace_headers)
        web_query = await _generate_web_query(query, rag_result)
        logger.info("Generated web search query (RAG_THEN_WEB): %r", web_query)
        web_result = await _call_a2a_safe(web_url, web_query, timeout, trace_headers=trace_headers)

    elif directive == "WEB_THEN_RAG":
        web_result = await _call_a2a(web_url, query, timeout, trace_headers=trace_headers)
        rag_result = await _call_a2a(rag_url, query, timeout, trace_headers=trace_headers)

    elif directive == "WEB_ONLY":
        web_result = await _call_a2a(web_url, query, timeout, trace_headers=trace_headers)
        sources = _extract_sources([web_result])
        web_result = re.sub(r'\[CONFIDENCE:[^\]]+\]\s*', '', web_result)
        web_result = _RAG_SOURCES_RE.sub('', web_result).rstrip()
        return {
            "answer": web_result,
            "sources": sources,
            "route": directive.lower(),
            "retrieved_context": [],
            "confidence": "n/a",
            "num_sources": len(sources),
        }

    # Summarise both findings (longer timeout: credibility checks + LLM)
    sum_input = (
        f"QUERY: {query}\n"
        f"WEB_FINDINGS: {web_result}\n"
        f"RAG_FINDINGS: {rag_result}"
    )
    final_answer = await _call_a2a(sum_url, sum_input, timeout * 3, trace_headers=trace_headers)
    if not final_answer:
        final_answer = web_result or rag_result

    all_texts = [rag_result, web_result, final_answer]
    confidence = _extract_confidence([rag_result])
    sources = _extract_sources(all_texts)
    final_answer = re.sub(r'\[CONFIDENCE:[^\]]+\]\s*', '', final_answer)
    final_answer = _RAG_SOURCES_RE.sub('', final_answer)
    _, final_answer = extract_trace(final_answer)
    final_answer = final_answer.rstrip()
    return {
        "answer": final_answer,
        "sources": sources,
        "route": directive.lower(),
        "retrieved_context": [rag_result, web_result],
        "confidence": confidence,
        "num_sources": len(sources),
    }


async def _run_confidence_gated(
    query: str,
    timeout: float,
    *,
    trace_headers: dict | None = None,
) -> dict:
    """Default path: RAG first, then confidence-gated web research via direct A2A calls.

    1. Call rag_lookup
    2. If confidence is HIGH → return RAG answer directly
    3. If MEDIUM or LOW → also call web_research + summariser
    """
    config = _config
    rag_url = config.rag_url
    web_url = config.web_research_url
    sum_url = config.summariser_url

    # Step 1: Always call RAG first
    rag_result = await _call_a2a(rag_url, query, timeout, trace_headers=trace_headers)
    confidence = _extract_confidence([rag_result])

    if confidence == "HIGH":
        sources = _extract_sources([rag_result])
        clean = re.sub(r'\[CONFIDENCE:[^\]]+\]\s*', '', rag_result)
        clean = _RAG_SOURCES_RE.sub('', clean).rstrip()
        _, clean = extract_trace(clean)
        logger.info("Confidence-gated: HIGH — returning RAG answer directly")
        return {
            "answer": clean,
            "sources": sources,
            "route": "rag_only",
            "retrieved_context": [rag_result],
            "confidence": confidence,
            "num_sources": len(sources),
        }

    # Step 2: LOW / MEDIUM — also call web research
    logger.info("Confidence-gated: %s — calling web_research + summariser", confidence)
    web_query = await _generate_web_query(query, rag_result)
    logger.info("Generated web search query: %r", web_query)
    web_result = await _call_a2a_safe(web_url, web_query, timeout, trace_headers=trace_headers)

    # Step 3: Summarise both findings (longer timeout: credibility checks + LLM)
    sum_input = (
        f"QUERY: {query}\n"
        f"WEB_FINDINGS: {web_result}\n"
        f"RAG_FINDINGS: {rag_result}"
    )
    final_answer = await _call_a2a(sum_url, sum_input, timeout * 3, trace_headers=trace_headers)
    if not final_answer:
        final_answer = web_result or rag_result

    all_texts = [rag_result, web_result, final_answer]
    sources = _extract_sources(all_texts)
    final_answer = re.sub(r'\[CONFIDENCE:[^\]]+\]\s*', '', final_answer)
    final_answer = _RAG_SOURCES_RE.sub('', final_answer)
    _, final_answer = extract_trace(final_answer)
    final_answer = final_answer.rstrip()
    return {
        "answer": final_answer,
        "sources": sources,
        "route": "rag_and_web",
        "retrieved_context": [rag_result, web_result],
        "confidence": confidence,
        "num_sources": len(sources),
    }


def _unwrap_a2a(text: str) -> str:
    """Strip {"result": "..."} A2A wrapper if the coordinator leaked it through."""
    stripped = text.strip()
    if stripped.startswith('{"result":'):
        try:
            return json.loads(stripped).get("result", text)
        except (json.JSONDecodeError, AttributeError):
            pass
    return text


async def _generate_web_query(original_query: str, rag_findings: str) -> str:
    """Ask the router LLM to derive a focused web search query from the user query + RAG output."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    model = os.environ.get("ROUTER_MODEL", "gpt-5.4")
    prompt = (
        "You are a search query generator. Given a user's question and what was already "
        "found in a local document corpus, output a single concise web search query "
        "(max 200 characters) that finds complementary or clarifying information online.\n\n"
        f"User question: {original_query}\n\n"
        f"Already found locally:\n{rag_findings[:600]}\n\n"
        "Output ONLY the search query, nothing else."
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80,
        temperature=0.3,
    )
    query = response.choices[0].message.content.strip()
    return query[:400]  # Tavily hard limit


def _extract_confidence(texts: list[str]) -> str:
    for text in texts:
        m = _CONFIDENCE_RE.search(text)
        if m:
            return m.group(1)
    # Fallback: read confidence from <rag_sources confidence="..."> attribute
    # (the ADK LLM sometimes strips [CONFIDENCE: ...] but preserves the tag)
    for text in texts:
        m = _RAG_CONFIDENCE_ATTR_RE.search(text)
        if m:
            return m.group(1)
    return "unknown"


@traceable(name="adk_coordinator", run_type="chain")
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
                final_answer = _unwrap_a2a(event.content.parts[0].text or "")

        if event.author in _SUB_AGENT_AUTHORS and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    sub_agent_texts.append(part.text)
                    if not event.is_final_response():
                        retrieved_context.append(part.text)

    return final_answer, retrieved_context, sub_agent_texts


@traceable(name="research_pipeline", run_type="chain")
async def _run_research(query: str, session_id: str) -> dict:
    """Core research logic wrapped as a LangSmith root trace."""
    logger.info("Research request started session=%s query=%r", session_id, query[:80])

    _get_config()  # ensure _config is initialized
    trace_headers = get_trace_headers()

    directive_raw = _detect_route_directive(query)
    if directive_raw:
        # Explicit routing: bypass ADK coordinator, call agents directly in Python
        directive = directive_raw.strip().strip("[]").replace("ROUTING: ", "")
        logger.info("Direct routing session=%s directive=%s", session_id, directive)
        return await _run_research_direct(query, directive, _config.a2a_timeout, trace_headers=trace_headers)

    # Default path: confidence-gated routing via direct A2A calls
    logger.info("Confidence-gated routing session=%s", session_id)
    overall_timeout = _config.a2a_timeout * 3
    try:
        result = await asyncio.wait_for(
            _run_confidence_gated(query, _config.a2a_timeout, trace_headers=trace_headers),
            timeout=overall_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Research timed out session=%s after %.1fs", session_id, _config.a2a_timeout)
        raise HTTPException(status_code=504, detail="Research timed out")

    logger.info(
        "Research completed session=%s confidence=%s route=%s chunks=%d sources=%d",
        session_id, result.get("confidence"), result.get("route"),
        len(result.get("retrieved_context", [])), result.get("num_sources", 0),
    )
    return result


@app.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    session_id = str(uuid.uuid4())
    try:
        result = await _run_research(request.query, session_id)
        return ResearchResponse(
            answer=result["answer"],
            sources=result["sources"],
            route=result["route"],
            retrieved_context=result["retrieved_context"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Orchestrator failed session=%s", session_id)
        raise HTTPException(status_code=500, detail="Internal research error") from exc


if __name__ == "__main__":
    port = int(os.environ.get("ORCHESTRATOR_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
