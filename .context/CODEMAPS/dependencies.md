<!-- Generated: 2026-04-19 | Files scanned: 87 | Token estimate: ~340 -->

# Dependencies

## External Services

| Service | Used By | Purpose |
|---|---|---|
| Tavily API | `mcp_tools/web_search`, `agents/web_research` | Web search results |
| OpenAI API | `mcp_tools/vector_db`, all agents | Embeddings (text-embedding-3-small), LLM calls |
| Qdrant | `mcp_tools/vector_db` | Vector storage for RAG |
| LangSmith | orchestrator + all agents + MCP clients | Runtime tracing (project: `research-app`) |

## Python Libraries

**MCP Tools** (all share): `fastmcp>=2.0`, `httpx>=0.27`, `python-dotenv>=1.0`, `pytest>=8.0`, `pytest-asyncio>=0.24`
- `web_search`: + `respx>=0.21`
- `vector_db`: + `qdrant-client>=1.9`, `openai>=1.0`
- `file_reader`: + `pymupdf>=1.24`, `respx>=0.21`
- `citation_checker`: + `respx>=0.21`

**Agents** (all share): `openai>=1.0`, `python-dotenv>=1.0`, `a2a-sdk`, `langsmith`, `pytest>=8.0`
- `web_research`: + `crewai`, `crewai-tools`, `tavily-python`
- `rag`: + `llama-index-core`, `llama-index-llms-openai`, `fastmcp>=2.0`
- `summariser`: + `fastmcp>=2.0`

**Orchestrator**: `google-adk`, `fastapi`, `uvicorn`, `fastmcp>=2.0`, `langsmith`, `python-dotenv`

**Frontend**: React 18, TypeScript, Vite, Tailwind CSS v4, Radix UI (shadcn/ui)

## Conda Environment

Name: `research-platform` (Python 3.11)

## Env Vars

| Var | Required By |
|---|---|
| `OPENAI_API_KEY` | vector_db, all agents |
| `TAVILY_API_KEY` | web_search, web_research agent |
| `QDRANT_URL` | vector_db (default: `http://localhost:6333`) |
| `LANGSMITH_API_KEY` | orchestrator + all agents (enables tracing) |
| `LANGSMITH_PROJECT` | orchestrator + all agents (default: `research-app`) |
| `LANGSMITH_ENDPOINT` | optional (EU endpoint: `https://eu.api.smith.langchain.com`) |
| `FILE_READER_BASE_DIR` | file_reader (optional path restriction) |
