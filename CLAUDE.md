# Research Platform — Claude Code Instructions

## Subagent Review Calibration

When using `superpowers:subagent-driven-development`, calibrate review intensity by task type:

### Scaffold / config-only tasks
*(requirements.txt, pytest.ini, __init__.py, .gitignore, Dockerfiles)*
- **Skip reviews entirely.** Verify inline by reading the files yourself.

### Test-only tasks
*(adding tests to an existing file, no logic changes)*
- **One combined spec+quality pass.** Not two separate rounds.
- If 3+ tests pass without issues, approve and move on.

### Implementation tasks
*(new .py files, changes to existing logic, new endpoints)*
- **Full two-stage review** (spec compliance first, then code quality).

### Red flags that justify extra review
- Implementer reports DONE_WITH_CONCERNS
- API/library behaviour differed from the plan
- Error handling or retry logic is involved

---

## Known API Facts (web_search MCP tool)

Discovered during Task 2 — do not re-litigate these:

- FastMCP `Client.call_tool()` raises `fastmcp.exceptions.ToolError`, not `McpError`
- `Client.call_tool()` result uses `result.content[0].text`, not `result[0].text`
- `McpError` constructor: `McpError(ErrorData(code=INTERNAL_ERROR, message="..."))` using integer constants from `mcp.types`
- `asyncio.sleep` patch path: `"mcp_tools.web_search.server.asyncio.sleep"`
- Conda env name: `research-platform`
- Run tests with: `conda run -n research-platform pytest mcp_tools/web_search/tests/test_server.py -v`

---

## Week 4 — ADK Orchestrator (week4-adk branch)

### Service Start Commands

All services must be started from `.worktrees/week4-adk/`:

```bash
# MCP tool servers
conda run -n research-platform python -m mcp_tools.web_search.server    # :9001
conda run -n research-platform python -m mcp_tools.vector_db.server      # :9002
conda run -n research-platform python -m mcp_tools.file_reader.server    # :9003
conda run -n research-platform python -m mcp_tools.citation_checker.server # :9004

# A2A agents
conda run -n research-platform python agents/web_research/main.py        # :8001
conda run -n research-platform python agents/rag/main.py                 # :8002
conda run -n research-platform python agents/summariser/main.py          # :8003

# Orchestrator — must run from worktree root
cd .worktrees/week4-adk && conda run -n research-platform python -m uvicorn orchestrator.main:app --port 8000

# Frontend
cd .worktrees/week4-adk/frontend && npm run dev                          # :5173
```

### RAG Agent Output Format

The RAG agent always emits this exact format — do not change the structure:

```
[CONFIDENCE: HIGH|MEDIUM|LOW]
<answer text>

<rag_sources>Title (url) | Title2 (url2)</rag_sources>
```

- Confidence thresholds: avg Qdrant score ≥0.75 → HIGH, ≥0.55 → MEDIUM, else LOW
- The `<rag_sources>` tag is how sources survive the coordinator LLM rewrite boundary
- The orchestrator strips `[CONFIDENCE: ...]` and `<rag_sources>` tags before returning the final answer

### Coordinator Routing Logic

1. **STEP 1**: Always delegate to `rag_lookup` first
2. **STEP 2**: If `[CONFIDENCE: HIGH]` → answer from RAG only; if MEDIUM or LOW → also call `web_research` → `summariser`
3. Summariser receives `QUERY:`, `WEB_FINDINGS:`, `RAG_FINDINGS:` sections

### ADK / A2A Gotchas

- Sub-agent event authors are: `rag_lookup`, `web_research`, `summariser`, `research_coordinator`, `user`
- Source extraction happens from raw sub-agent event text (before coordinator rewrites it) — see `_collect_events()` in `orchestrator/main.py`
- `conda run` launchers die before the child uvicorn process — start uvicorn directly when debugging stdout
- The orchestrator must be started from the worktree root (`.worktrees/week4-adk/`) for relative module imports to resolve

### Corpus Endpoints (week4-adk only)

```
POST /corpus        — ingest document {title, content, url, collection}
GET  /corpus        — list corpus documents
POST /corpus/upload — multipart file upload (PDF/.txt/.md) → {text}
```

PDF upload calls `file_reader` MCP (`read_file` tool) via a temp file; result is `json.loads(result.content[0].text)["text"]`.
