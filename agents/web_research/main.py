"""Web research A2A agent server — direct passthrough, no LLM intermediary."""
import logging
import os
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agents.web_research.agent import run_web_research

load_dotenv()

logger = logging.getLogger(__name__)

_PORT = int(os.environ.get("WEB_RESEARCH_PORT", 8001))
_HOST = os.environ.get("WEB_RESEARCH_HOST", "localhost")

_AGENT_CARD = {
    "name": "web_research",
    "description": "Searches the web for recent information on a given topic.",
    "url": f"http://{_HOST}:{_PORT}",
    "version": "0.0.1",
    "protocolVersion": "0.3.0",
    "preferredTransport": "JSONRPC",
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "capabilities": {},
    "supportsAuthenticatedExtendedCard": False,
    "skills": [
        {
            "id": "web_research",
            "name": "web_research",
            "description": "Search the web for recent information about the given query.",
            "tags": ["llm", "tools"],
            "examples": [],
        }
    ],
}

app = FastAPI(title="web_research A2A server")


@app.get("/.well-known/agent-card.json")
async def agent_card() -> dict:
    return _AGENT_CARD


@app.post("/")
async def handle_jsonrpc(request: Request) -> JSONResponse:
    body = await request.json()
    rpc_id = body.get("id", 1)
    method = body.get("method", "")

    if method != "message/send":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        })

    try:
        parts = body["params"]["message"]["parts"]
        query = next(p["text"] for p in parts if p.get("kind") == "text")
    except (KeyError, StopIteration, TypeError):
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32600, "message": "Invalid request: missing query text"},
        })

    logger.info("web_research query=%r", query[:80])
    result = await run_web_research(query)

    context_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "kind": "task",
            "id": task_id,
            "contextId": context_id,
            "artifacts": [
                {
                    "artifactId": str(uuid.uuid4()),
                    "parts": [{"kind": "text", "text": result}],
                }
            ],
            "history": [],
            "metadata": {},
            "status": {"state": "completed"},
        },
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
