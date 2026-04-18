<!-- Generated: 2026-04-11 | Week 4+5 complete -->

# Dependencies

## External Services & APIs

| Service | Used By | Purpose | Auth |
|---------|---------|---------|------|
| Tavily API | `mcp_tools/web_search` | Web search results | `TAVILY_API_KEY` |
| OpenAI API | Orchestrator + all agents (gpt-4o-mini) + evals | LLM inference via LiteLlm + embeddings + judge | `OPENAI_API_KEY` |
| Qdrant Cloud/Local | `mcp_tools/vector_db` | Vector storage for RAG | `QDRANT_URL` |
| LangSmith | Orchestrator + evals/run_evals.py | Tracing, dataset management, eval runs | `LANGSMITH_API_KEY` |

## Core Stack (All Layers)

| Library | Version | Used By | Purpose |
|---------|---------|---------|---------|
| **google-adk** | >=1.0 | orchestrator, agents | ADK Agent, Runner, RemoteA2aAgent, FunctionTool, LiteLlm |
| **a2a-python** | >=0.3 | agents, orchestrator | Agent-to-agent JSON-RPC 2.0 protocol, agent-card.json |
| **fastapi** | >=0.115 | orchestrator, agents | HTTP server for endpoints & A2A protocol |
| **uvicorn** | >=0.30 | orchestrator, agents | ASGI server for FastAPI |
| **httpx** | >=0.27 | mcp_tools, agents, evals | Async HTTP client for MCP + API calls + eval orchestration |
| **langsmith** | >=0.2 | orchestrator, evals | Tracing, dataset CRUD, eval framework |

## Orchestrator Stack (`orchestrator/requirements.txt`)

```
google-adk>=1.0          # ADK: Agent, Runner, RemoteA2aAgent, LiteLlm, FunctionTool
langsmith>=0.2           # LangSmith tracing (optional, disabled by default)
httpx>=0.27              # Async HTTP client
fastapi>=0.115           # Web framework + A2A protocol handler
uvicorn>=0.30            # ASGI server
python-dotenv>=1.0       # .env loading (OrchestratorConfig.from_env)
pydantic>=2.0            # Dataclass validation (OrchestratorConfig frozen=True)
pytest>=8.0              # Unit testing
pytest-asyncio>=0.24     # Async test support
a2a-python>=0.3          # A2A protocol (implicit via google-adk)
```

**Key entry point**: `orchestrator/main.py` (FastAPI app + lazy Runner init)
**Key config**: `orchestrator/config.py` (OrchestratorConfig frozen dataclass, 6 env vars)

## Agent Stack (All 3 Agents)

Agents inherit from conda env (no per-agent requirements.txt). Import chain:

- `agents/{web_research|rag|summariser}/main.py`: Imports agent.py, to_a2a, FunctionTool
- `agents/{web_research|rag|summariser}/agent.py`: Domain-specific logic (CrewAI, LlamaIndex, Anthropic)
- `agents/{web_research|rag|summariser}/mcp_client.py`: FastMCP HTTP client → MCP tool server

**Shared dependencies** (from conda env or orchestrator requirements):
```
google-adk>=1.0          # Agent, FunctionTool, LiteLlm
crewai>=0.80             # agents/web_research/agent.py
llama-index>=0.12        # agents/rag/agent.py
anthropic>=0.40          # agents/summariser/agent.py (optional, not in current code)
fastmcp>=2.0             # FastMCP HTTP client (agents/*/mcp_client.py)
httpx>=0.27              # Underlying HTTP transport
python-dotenv>=1.0       # .env loading
```

## Evals Stack (`evals/`)

New in Week 5. Measures faithfulness, relevance, citation accuracy via LangSmith.

```
langsmith>=0.2           # Client, evaluate(), dataset CRUD
openai>=1.0              # Judge LLM (gpt-4-turbo for evaluators)
httpx>=0.27              # HTTP client to orchestrator POST /research
python-dotenv>=1.0       # .env loading
```

**Key entry point**: `evals/run_evals.py`
- Loads dataset.json (25 Q&A pairs) → LangSmith dataset
- Calls orchestrator POST /research for each example
- Runs 3 evaluators in parallel (max_concurrency=4)
- Returns LangSmith Experiment with metric scores

**Key modules**:
- `evals/_client.py`: `call_research_endpoint(query, base_url)` → httpx POST
- `evals/dataset_loader.py`: `ensure_langsmith_dataset()` + `load_local_dataset()`
- `evals/evaluators/faithfulness.py`: Judge context grounding
- `evals/evaluators/relevance.py`: Judge query coverage + topic matches
- `evals/evaluators/citation_accuracy.py`: Regex + judge for source citations
- `evals/evaluators/_judge.py`: Shared judge() function (calls OpenAI gpt-4)

**Report tool**: `evals/report.py` — Compare two experiment names, show delta table

## MCP Tool Servers (FastMCP)

All in `mcp_tools/` with ~93 total unit tests. Unchanged from Week 3.

### web_search (port 9001) → Tavily
```
fastmcp>=2.0, httpx>=0.27, python-dotenv>=1.0
search_web(query, num_results=5, search_depth="basic", include_answer=False)
→ JSON {query, results:[{title, url, content, score}], answer?}
```

### vector_db (port 9002) → Qdrant + OpenAI
```
fastmcp>=2.0, qdrant-client>=1.9, openai>=1.0, python-dotenv>=1.0
ingest_document(title, content, url, collection="documents", chunk_size=1000, overlap=200)
→ JSON {document_id, chunks_stored, title}
search_documents(query, collection="documents", num_results=5)
→ JSON {query, collection, results:[{title, url, content, score}]}
```

### file_reader (port 9003) → Local FS / Remote URLs
```
fastmcp>=2.0, pymupdf>=1.24, httpx>=0.27, python-dotenv>=1.0
read_file(source, start_page=1, end_page=None)
→ JSON {source, file_type, text, metadata:{title, author, page_count, pages_read}}
```

### citation_checker (port 9004) → Domain scoring + HTTP HEAD
```
fastmcp>=2.0, httpx>=0.27, python-dotenv>=1.0
check_credibility(url) → JSON {url, score, label, reason}
check_reachability(url) → JSON {url, reachable, status_code, latency_ms, final_url}
```

## Environment Variables

### Orchestrator (`orchestrator/config.py`)
- `WEB_RESEARCH_AGENT_URL` (default: `http://localhost:8001`)
- `RAG_AGENT_URL` (default: `http://localhost:8002`)
- `SUMMARISER_AGENT_URL` (default: `http://localhost:8003`)
- `ROUTER_MODEL` (default: `gpt-4o-mini`)
- `A2A_TIMEOUT` (default: `30.0` seconds)
- `LANGSMITH_PROJECT` (default: `research-platform`)

### Agents (injected to main.py)
- `WEB_RESEARCH_PORT` (default: 8001), `RAG_PORT` (default: 8002), `SUMMARISER_PORT` (default: 8003)
- `ROUTER_MODEL` (default: `gpt-4o-mini`) — shared with orchestrator
- `WEB_SEARCH_MCP_URL` (default: `http://localhost:9001/mcp`)
- `VECTOR_DB_MCP_URL` (default: `http://localhost:9002/mcp`)
- `FILE_READER_MCP_URL` (default: `http://localhost:9003/mcp`)
- `CITATION_CHECKER_MCP_URL` (default: `http://localhost:9004/mcp`)

### Evals (`evals/run_evals.py`)
- `LANGSMITH_API_KEY` (required)
- `OPENAI_API_KEY` (required for judge LLM)
- Base URL via `--base-url` flag (default: `http://localhost:8000`)

### MCP Tools
- `TAVILY_API_KEY` (required for web_search)
- `QDRANT_URL` (required for vector_db)
- `OPENAI_API_KEY` (required for embeddings in vector_db)
- `FILE_READER_BASE_DIR` (optional for file_reader, restricts local path access)

## Conda Environment

**Name**: `research-platform` (Python 3.11)

**Installation**:
```bash
conda env create -f environment.yml
conda activate research-platform
pip install -r orchestrator/requirements.txt
```

## Breaking Changes (Week 3 → Week 4 → Week 5)

| Aspect | Week 3 | Week 4 | Week 5 |
|--------|--------|--------|--------|
| **Orchestrator framework** | LangGraph StateGraph | ADK Agent + Runner | ADK Agent + Runner (same) |
| **Routing logic** | Hardcoded node graph | LLM-driven via agent instruction | LLM-driven (same) |
| **Session management** | Manual | ADK InMemorySessionService | ADK InMemorySessionService + cleanup |
| **Sub-agent framework** | CrewAI, LlamaIndex, Anthropic SDK | CrewAI, LlamaIndex, Anthropic SDK (same) | (same) |
| **Agent-to-agent protocol** | A2A (unchanged) | A2A (unchanged) | A2A (unchanged) |
| **Eval pipeline** | None | None | LangSmith (NEW) |
| **LLM client** | LangChain LLM | LiteLlm (google-adk) | LiteLlm (same) |
