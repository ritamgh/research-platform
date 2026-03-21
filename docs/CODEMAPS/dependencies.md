<!-- Generated: 2026-03-21 | Files scanned: 8 | Token estimate: ~300 -->

# Dependencies

## External Services

| Service | Used By | Purpose |
|---|---|---|
| Tavily API | `mcp_tools/web_search` | Web search results |
| Anthropic API | `agents/summariser` (planned), evals | Summarisation, LLM-as-judge |
| LangSmith | orchestrator + all agents (planned) | Tracing, eval datasets |
| Qdrant | `mcp_tools/vector_db` (active) | Vector storage for RAG |

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
openai>=1.30        # embeddings (text-embedding-3-small)
python-dotenv>=1.0  # .env loading
pytest>=8.0
pytest-asyncio>=0.24
```

## Planned Libraries (from project spec)

```
langchain>=0.3 / langgraph>=0.2   # orchestrator
langsmith>=0.1                     # tracing + evals
anthropic>=0.40                    # summariser agent + evaluators
crewai>=0.80                       # web_research agent
llama-index>=0.12                  # rag agent
a2a-python>=0.3                    # agent-to-agent protocol
faiss-cpu>=1.8                     # vector search
pymupdf>=1.24                      # PDF parsing
tavily-python>=0.5                 # Tavily SDK (alt to raw httpx)
```

## Conda Environment

Name: `research-platform` (Python 3.11)
