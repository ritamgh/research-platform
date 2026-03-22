<!-- Generated: 2026-03-22 | Files scanned: 15 | Token estimate: ~420 -->

# Architecture

## System Overview

Multi-agent research platform. User submits a question → orchestrator routes to specialized agents → agents use MCP tool servers → results synthesized and returned.

```
User Query
    │
    ▼
Orchestrator (LangGraph) ──── A2A Protocol ────► Web Research Agent (CrewAI)
    │                                                      │ MCP
    │                         A2A Protocol ────► RAG Agent (LlamaIndex)
    │                                                      │ MCP
    └─────────────────────── A2A Protocol ────► Summariser Agent (Anthropic SDK)
                                                           │
                                              ┌────────────▼────────────┐
                                              │   MCP Tool Servers      │
                                              │  web_search  vector_db  │
                                              │  file_reader citation   │
                                              └─────────────────────────┘
                                                           │
                                              LangSmith (traces + evals)
```

## Build Status (Week 1 of 4 — complete)

| Component | Status | Port |
|---|---|---|
| `mcp_tools/web_search` | ✅ Built | 9001 |
| `mcp_tools/vector_db` | ✅ Built | 9002 |
| `mcp_tools/file_reader` | ✅ Built | 9003 |
| `mcp_tools/citation_checker` | ✅ Built | 9004 |
| `agents/web_research` | ⬜ Planned | 8001 |
| `agents/rag` | ⬜ Planned | 8002 |
| `agents/summariser` | ⬜ Planned | 8003 |
| `orchestrator` | ⬜ Planned | 8000 |

All four Week 1 MCP tool servers are now complete. The most recent completion is
`citation_checker`, which provides two tools: `check_credibility` (offline domain/TLD
heuristics) and `check_reachability` (HTTP HEAD + latency measurement).

## Key Protocols

- **MCP**: agents → tool servers (tool discovery + invocation)
- **A2A**: orchestrator → agents (Agent Cards at `/.well-known/agent.json`)
- **LangSmith**: tracing throughout, eval pipeline on completion
