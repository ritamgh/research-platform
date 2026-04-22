# Multi-Agent Research Platform

A multi-agent research pipeline built to understand **Google ADK**, **A2A (Agent-to-Agent) protocol**, and **MCP (Model Context Protocol)** in practice.

A user asks a research question. The orchestrator routes it through a RAG agent (checks local documents first), gates on confidence, calls a web research agent if needed, and synthesises both into a cited answer. Every step is traced end-to-end in LangSmith.

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────┐
│   Orchestrator  (Google ADK + FastAPI)       │
│   Confidence-gated routing via ADK coordinator│
│   POST /research  :8000                      │
└──────────┬───────────────────┬──────────────┘
           │  A2A protocol     │
           ▼                   ▼
┌──────────────────┐  ┌──────────────────────┐
│   RAG Agent      │  │  Web Research Agent  │
│   LlamaIndex     │  │  CrewAI              │
│   :8002          │  │  :8001               │
└────────┬─────────┘  └──────────┬───────────┘
         │ MCP                   │ MCP
         ▼                       ▼
  ┌─────────────┐        ┌──────────────┐
  │  vector_db  │        │  web_search  │
  │  :9002      │        │  :9001       │
  └─────────────┘        └──────────────┘
           │
           ▼
┌──────────────────────┐
│   Summariser Agent   │
│   OpenAI SDK         │
│   :8003              │
└──────────┬───────────┘
           │ MCP
           ▼
  ┌──────────────────┐
  │ citation_checker │
  │ :9004            │
  └──────────────────┘
           │
           ▼
  LangSmith (distributed traces)
```

### Routing logic

1. **Always** delegate to RAG agent first
2. RAG returns `[CONFIDENCE: HIGH | MEDIUM | LOW]`
3. `HIGH` → return RAG answer directly
4. `MEDIUM / LOW` → LLM generates a focused web search query from the RAG output + original question → calls web research agent → both findings go to summariser

---

## Stack

| Layer | Tech |
|---|---|
| Orchestrator | Google ADK, FastAPI |
| Agent protocol | A2A (ADK `RemoteA2aAgent`) |
| Tool protocol | MCP (FastMCP) |
| RAG agent | LlamaIndex + Qdrant |
| Web research agent | CrewAI + Tavily |
| Summariser agent | OpenAI SDK |
| Embeddings | `text-embedding-3-small` |
| Models | `gpt-5.4` (orchestrator), `gpt-5.4-mini` (agents) |
| Tracing | LangSmith (distributed, cross-agent) |
| Frontend | React + Vite + shadcn/ui |

---

## Services

| Service | Port | Description |
|---|---|---|
| Orchestrator | 8000 | `POST /research`, `POST /corpus`, `GET /corpus` |
| Web Research Agent | 8001 | A2A server — CrewAI + Tavily |
| RAG Agent | 8002 | A2A server — LlamaIndex + Qdrant |
| Summariser Agent | 8003 | A2A server — OpenAI SDK |
| web_search MCP | 9001 | Tavily wrapper |
| vector_db MCP | 9002 | Qdrant read/write + embeddings |
| file_reader MCP | 9003 | PDF / text extraction |
| citation_checker MCP | 9004 | URL credibility scoring |
| Frontend | 5173 | React dev server |

---

## Running Locally

### Prerequisites

- Python 3.11+ with a `research-platform` conda env (or any venv)
- Node 18+
- Qdrant running locally: `docker run -p 6333:6333 qdrant/qdrant`
- API keys: OpenAI, Tavily, LangSmith

### Setup

```bash
git clone https://github.com/ritamgh/research-platform
cd research-platform
cp .env.example .env
# fill in OPENAI_API_KEY, TAVILY_API_KEY, LANGSMITH_API_KEY
pip install -r orchestrator/requirements.txt
cd frontend && npm install
```

### Start all services

```bash
# MCP tool servers
python -m mcp_tools.web_search.server       # :9001
python -m mcp_tools.vector_db.server        # :9002
python -m mcp_tools.file_reader.server      # :9003
python -m mcp_tools.citation_checker.server # :9004

# A2A agents
python agents/web_research/main.py          # :8001
python agents/rag/main.py                   # :8002
python agents/summariser/main.py            # :8003

# Orchestrator
uvicorn orchestrator.main:app --port 8000

# Frontend
cd frontend && npm run dev                  # :5173
```

### Quick test

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{"query": "What is mechanistic interpretability?"}'
```

---

## LangSmith Tracing

Each agent wraps its work in a `tracing_context` so spans appear as children of the orchestrator's root trace. The orchestrator encodes LangSmith trace headers into a `__LST__...__LST__` prefix on every A2A message, which each agent extracts and uses to continue the trace chain.

A single LangSmith trace shows the full pipeline: routing decision → RAG lookup → (if needed) web query generation → web research → summarisation — all in one waterfall.

---

## What I Built This To Learn

- **MCP**: writing tool *servers*, not just consuming them — the `list_tools` / `call_tool` contract and HTTP transport via FastMCP
- **A2A**: how agents from different frameworks (CrewAI, LlamaIndex, OpenAI SDK) interoperate over a common protocol — each agent is independently deployable and framework-agnostic from the outside
- **Google ADK**: `RemoteA2aAgent`, `Runner`, `InMemorySessionService`, and how the coordinator orchestrates sub-agents via natural language instructions
- **Distributed tracing**: propagating LangSmith trace context across HTTP boundaries so a multi-service pipeline produces a single coherent trace

---

## Project Structure

```
research-platform/
├── orchestrator/
│   ├── main.py           # FastAPI app, routing logic, _generate_web_query
│   ├── coordinator.py    # ADK coordinator with RemoteA2aAgent sub-agents
│   └── config.py         # OrchestratorConfig from env
├── agents/
│   ├── web_research/     # CrewAI agent + FastMCP client
│   ├── rag/              # LlamaIndex agent + FastMCP client
│   └── summariser/       # OpenAI SDK agent + FastMCP client
├── mcp_tools/
│   ├── web_search/       # Tavily MCP server
│   ├── vector_db/        # Qdrant MCP server
│   ├── file_reader/      # PDF/text MCP server
│   └── citation_checker/ # URL credibility MCP server
├── common/
│   └── tracing.py        # LangSmith trace context propagation helpers
├── frontend/             # React + Vite + shadcn/ui
└── .env.example
```
