<!-- Generated: 2026-03-22 | Files scanned: 15 | Token estimate: ~360 -->

# Dependencies

## External Services

| Service | Used By | Purpose |
|---|---|---|
| Tavily API | `mcp_tools/web_search` | Web search results |
| Anthropic API | `agents/summariser` (planned), evals | Summarisation, LLM-as-judge |
| LangSmith | orchestrator + all agents (planned) | Tracing, eval datasets |
| Qdrant | `mcp_tools/vector_db` | Vector storage for RAG |

## Python Libraries (installed)

**`mcp_tools/web_search` — `requirements.txt`:**
```
fastmcp>=2.0        # MCP server framework
httpx>=0.27         # async HTTP client
python-dotenv>=1.0  # .env loading
pytest>=8.0
pytest-asyncio>=0.24
respx>=0.21         # httpx mock for tests
```

**`mcp_tools/vector_db` — `requirements.txt`:**
```
fastmcp>=2.0        # MCP server framework
qdrant-client>=1.9  # Qdrant vector DB client
openai>=1.0         # embeddings (text-embedding-3-small)
python-dotenv>=1.0  # .env loading
pytest>=8.0
pytest-asyncio>=0.24
```

**`mcp_tools/file_reader` — `requirements.txt`:**
```
fastmcp>=2.0        # MCP server framework
pymupdf>=1.24       # PDF parsing (fitz)
httpx>=0.27         # async HTTP client for remote URLs
python-dotenv>=1.0  # .env loading
pytest>=8.0
pytest-asyncio>=0.24
respx>=0.21         # httpx mock for tests
```

**`mcp_tools/citation_checker` — `requirements.txt`:**
```
fastmcp>=2.0        # MCP server framework
httpx>=0.27         # async HTTP client for reachability checks
python-dotenv>=1.0  # .env loading
pytest>=8.0
pytest-asyncio>=0.24
respx>=0.21         # httpx mock for tests
```

## Shared Dependencies

The four MCP tool servers share these common dependencies:
- **fastmcp>=2.0** — all servers
- **httpx>=0.27** — web_search, file_reader, citation_checker (for HTTP calls)
- **python-dotenv>=1.0** — all servers
- **pytest>=8.0, pytest-asyncio>=0.24, respx>=0.21** — test suites in all servers

Note: respx is used to mock httpx calls in unit tests; qdrant-client and pymupdf are tool-specific.

## Planned Libraries (from project spec)

```
langchain>=0.3 / langgraph>=0.2   # orchestrator
langsmith>=0.1                     # tracing + evals
anthropic>=0.40                    # summariser agent + evaluators
crewai>=0.80                       # web_research agent
llama-index>=0.12                  # rag agent
a2a-python>=0.3                    # agent-to-agent protocol
faiss-cpu>=1.8                     # vector search
tavily-python>=0.5                 # Tavily SDK (alt to raw httpx)
```

## Conda Environment

Name: `research-platform` (Python 3.11)
