<!-- Generated: 2026-04-19 | Files scanned: 87 | Token estimate: ~420 -->

# Architecture

## System Overview

Multi-agent research platform (single branch: main). User submits query via React UI or HTTP → ADK orchestrator routes to agents → agents call MCP tools → results returned with LangSmith traces.

```
User Query (React UI :5173 or HTTP)
    │
    ▼
Orchestrator (Google ADK Runner, port 8000)
│  research_coordinator (LiteLlm/gpt-4o-mini)
│  @traceable: research_pipeline → adk_coordinator
│
│  STEP 1: always → rag_lookup (RemoteA2aAgent :8002)
│      RAG returns [CONFIDENCE: HIGH|MEDIUM|LOW] + <rag_sources>
│  STEP 2: HIGH → answer from RAG only
│          MEDIUM|LOW → web_research → summariser
│
│  ┌─── A2A ───► web_research agent (port 8001)
│  │                  └── MCP → web_search (port 9001, Tavily)
│  ├─── A2A ───► rag agent (port 8002)
│  │                  └── MCP → vector_db (port 9002, Qdrant)
│  │                  └── MCP → file_reader (port 9003, PyMuPDF)
│  └─── A2A ───► summariser agent (port 8003)
│                     └── MCP → citation_checker (port 9004)
└──────────────────────────────────────────────────────────────────
    │
    ▼
LangSmith (project: research-app)
  Traces: research_pipeline, adk_coordinator, rag_lookup, web_research,
          summariser, mcp_search_documents, mcp_search_web, mcp_check_credibility
```

## Component Status

| Component | Branch | Port | Notes |
|---|---|---|---|
| `mcp_tools/web_search` | main | 9001 | Tavily |
| `mcp_tools/vector_db` | main | 9002 | Qdrant + OpenAI embeddings |
| `mcp_tools/file_reader` | main | 9003 | PyMuPDF |
| `mcp_tools/citation_checker` | main | 9004 | |
| `agents/web_research` | main | 8001 | CrewAI + Tavily MCP |
| `agents/rag` | main | 8002 | LlamaIndex + Qdrant, confidence scoring |
| `agents/summariser` | main | 8003 | AsyncOpenAI + wrap_openai |
| `orchestrator` | main | 8000 | Google ADK, ADK RAG-first routing |
| `frontend` | main | 5173 | React 18/Vite, Research + Corpus tabs |

## Key Protocols

- **MCP**: agents → tool servers via FastMCP HTTP transport
- **A2A**: orchestrator → agents via Agent Cards at `/.well-known/agent-card.json`
- **Confidence**: Qdrant similarity avg ≥0.75→HIGH, ≥0.55→MEDIUM, else LOW → gates web fallback
- **Source pass-through**: `<rag_sources>` XML tag survives coordinator LLM rewrite; stripped before response
