<!-- Generated: 2026-04-19 | Files scanned: 87 | Token estimate: ~520 -->

# Backend

## Orchestrator (Google ADK, port 8000)

```
POST /research  →  ResearchRequest{query}
    → _run_research() [@traceable: research_pipeline]
    → _collect_events() [@traceable: adk_coordinator]
    → ADK Runner → research_coordinator (LiteLlm/gpt-4o-mini)
    → STEP 1: always → rag_lookup (RemoteA2aAgent :8002)
        RAG returns [CONFIDENCE: HIGH|MEDIUM|LOW] + <rag_sources>...</rag_sources>
    → STEP 2: if HIGH → answer from RAG only
              if MEDIUM|LOW → also → web_research (RemoteA2aAgent :8001) → summariser
    → _extract_confidence() → logged to LangSmith trace metadata
    → ResearchResponse{answer, sources, route="adk", retrieved_context}

POST /corpus        → ingest_document → vector_db MCP (ingest_document tool)
GET  /corpus        → list_corpus → vector_db MCP (list_documents tool)
POST /corpus/upload → extract_file_text (UploadFile) → file_reader MCP (read_file) → {text}
GET  /health        → {"status": "ok"}
```

Key files:
- `orchestrator/main.py` — FastAPI app, lifespan, `_run_research`, `_collect_events`, corpus endpoints (300 lines)
- `orchestrator/coordinator.py` — ADK Agent + RemoteA2aAgents, COORDINATOR_INSTRUCTION (58 lines)
- `orchestrator/config.py` — OrchestratorConfig.from_env() (frozen dataclass)

LangSmith: `LANGCHAIN_TRACING_V2` set in lifespan if `LANGSMITH_API_KEY` present; project = `LANGSMITH_PROJECT` (default `research-app`).

## Agents

### web_research (port 8001)
```
A2A /.well-known/agent-card.json
POST / → run_web_research(query) [@traceable: web_research]
       → search_web MCP [@traceable: mcp_search_web]
       → CrewAI Task → LLM synthesis
```
- `agents/web_research/agent.py` — CrewAI crew, single Tavily call, URL injection (143 lines)
- `agents/web_research/mcp_client.py` — FastMCP client for web_search :9001

### rag (port 8002)
```
A2A /.well-known/agent-card.json
POST / → run_rag_lookup(query) [@traceable: rag_lookup]
       → search_documents MCP [@traceable: mcp_search_documents]
       → LlamaIndex OpenAI synthesis (llm.acomplete)
       → adds metadata: {confidence, avg_score, num_chunks} to LangSmith trace
```
- `agents/rag/agent.py` — RAG pipeline, confidence scoring, `<rag_sources>` tag (92 lines)
  - Emits: `[CONFIDENCE: X]\n<answer>\n\n<rag_sources>title (url) | ...</rag_sources>`
- `agents/rag/mcp_client.py` — FastMCP clients for vector_db :9002 + file_reader :9003

### summariser (port 8003)
```
A2A /.well-known/agent-card.json
POST / → run_summariser(query, web_findings, rag_findings) [@traceable: summariser]
       → check_credibility MCP [@traceable: mcp_check_credibility] (per URL, cap 10)
       → wrap_openai(AsyncOpenAI) → chat.completions.create [child LLM span in LangSmith]
```
- `agents/summariser/agent.py` — URL extraction, credibility filter, synthesis prompt (102 lines)
- `agents/summariser/mcp_client.py` — FastMCP client for citation_checker :9004

## LangSmith Trace Hierarchy (per /research request)

```
research_pipeline (chain)
└── adk_coordinator (chain)          ← ADK Runner execution time
    [independent per-agent traces, correlatable by session_id metadata]

rag_lookup (chain)                   ← per agent process
└── mcp_search_documents (tool)

web_research (chain)
└── mcp_search_web (tool)

summariser (chain)
├── mcp_check_credibility (tool)     ← per URL
└── OpenAI ChatCompletion (llm)      ← via wrap_openai
```
