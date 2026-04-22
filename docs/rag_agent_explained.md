# RAG Agent — Deep Dive Explanation

This document explains every file, function, and line of the RAG agent (`agents/rag/`).

---

## What is RAG?

**Retrieval-Augmented Generation** is a technique that grounds an LLM's answer in real documents instead of relying on its training memory. The pattern is always:

1. **Retrieve** — find relevant text chunks from a document store
2. **Augment** — inject those chunks into the prompt as context
3. **Generate** — ask the LLM to answer *only* based on what was retrieved

This agent implements that pattern using:
- The **vector_db MCP server** (port 9002) for retrieval
- **LlamaIndex's Anthropic wrapper** for generation

---

## File Map

```
agents/rag/
├── agent_card.json      — declares the agent's identity to the A2A network
├── mcp_client.py        — thin async wrappers for talking to MCP tool servers
├── agent.py             — core RAG logic (retrieve → parse → generate)
├── main.py              — FastAPI server + A2A protocol wiring
└── tests/
    ├── conftest.py      — sets fake env vars so tests don't need real API keys
    └── test_agent.py    — unit tests for all layers
```

---

## `agent_card.json`

```json
{
  "name": "rag-agent",
  "description": "Retrieves relevant information from the local document corpus...",
  "version": "1.0.0",
  "url": "http://localhost:8002",
  "capabilities": { "streaming": false, "push_notifications": false },
  "skills": [
    {
      "id": "rag_lookup",
      "name": "RAG Lookup",
      "description": "Given a research question, searches the local document corpus...",
      "tags": ["rag", "retrieval", "documents", "vector-search"],
      "examples": [...]
    }
  ]
}
```

**What it is:** A static JSON manifest. When the server starts, `main.py` reads this file and serves it at `/.well-known/agent.json`. Any A2A-compatible orchestrator (like our LangGraph orchestrator in Week 3) can `GET /.well-known/agent.json` to discover what this agent can do and how to call it.

**Key fields:**
- `name` — machine-readable identifier used by the orchestrator to route requests
- `url` — where the agent listens; can be overridden by the `RAG_AGENT_URL` env var at runtime
- `skills[].id` — the capability being advertised (`rag_lookup`); this is what other agents ask for
- `capabilities.streaming: false` — this agent returns one complete response, not a stream

---

## `mcp_client.py`

```python
import os
from fastmcp import Client

VECTOR_DB_MCP_URL = os.environ.get("VECTOR_DB_MCP_URL", "http://localhost:9002")
FILE_READER_MCP_URL = os.environ.get("FILE_READER_MCP_URL", "http://localhost:9003")
```

**Lines 5–6:** Module-level constants that read the MCP server addresses from environment variables. The `os.environ.get("X", default)` pattern means:
- In production: set `VECTOR_DB_MCP_URL=http://vector-db-service:9002` in your env
- In development/tests: falls back to `http://localhost:9002` automatically

These are read *once at import time*, which is why the test `test_url_env_vars` uses `importlib.reload(mod)` after setting the env var — it needs to force a re-import so the constants pick up the new values.

---

### `search_documents(query, top_k=5)`

```python
async def search_documents(query: str, top_k: int = 5) -> str:
    async with Client(VECTOR_DB_MCP_URL) as client:
        result = await client.call_tool(
            "search_documents",
            {"query": query, "top_k": top_k},
        )
        return result.content[0].text
```

**Line by line:**

| Line | What it does |
|------|-------------|
| `async def` | This is a coroutine — it must be `await`ed by the caller. It doesn't block the event loop while waiting for the HTTP response. |
| `top_k: int = 5` | Default: fetch the 5 most relevant chunks. Callers can raise this for broader recall or lower it to keep the prompt short. |
| `async with Client(...) as client` | Opens an HTTP connection to the vector_db MCP server, yields a `client` object, then closes the connection when the block exits — even if an exception is raised. `async with` is the async version of a regular context manager. |
| `client.call_tool("search_documents", {...})` | Sends a JSON-RPC request to the MCP server asking it to run its `search_documents` tool. The dict is the tool's input schema. |
| `result.content[0].text` | MCP tool results are wrapped in a `CallToolResult` object. `.content` is a list of content blocks (usually just one). `.text` extracts the raw string — in this case, a JSON array of document hits. |

**What comes back:** A JSON string like:
```json
[
  {"content": "Attention mechanisms allow models...", "source": "paper1.pdf"},
  {"content": "Transformers use multi-head self-attention.", "source": "paper2.pdf"}
]
```

---

### `read_file(source)`

```python
async def read_file(source: str) -> str:
    async with Client(FILE_READER_MCP_URL) as client:
        result = await client.call_tool("read_file", {"source": source})
        return result.content[0].text
```

Same pattern as `search_documents` but talks to the **file_reader MCP** (port 9003). `source` can be a local file path or a URL. This function is defined here for completeness but is not yet called by `agent.py` — it's available for future use when the agent needs to fetch the full text of a document that was surfaced by vector search.

---

## `agent.py`

This is the brain of the agent — it orchestrates the full RAG pipeline.

### Imports

```python
from llama_index.core import Settings
from llama_index.core.llms import LLM
from llama_index.llms.anthropic import Anthropic
```

- `llama_index.core.llms.LLM` — the base class/type for all LlamaIndex LLM wrappers. Used as the return type annotation on `_get_llm()`.
- `llama_index.llms.anthropic.Anthropic` — LlamaIndex's wrapper around the Anthropic API. It handles auth, model selection, and exposes `.acomplete()` (async completion).
- `Settings` — imported but not explicitly used in the current code; it's LlamaIndex's global config object (could be used to set a default LLM globally).

```python
from agents.rag.mcp_client import search_documents, read_file
```

Imports the two async functions defined in `mcp_client.py`. `search_documents` is used as the default retrieval function. `read_file` is imported for potential future use.

---

### `_get_llm()` — LLM factory

```python
def _get_llm() -> LLM:
    return Anthropic(
        model=os.environ.get("RAG_LLM", "claude-haiku-4-5-20251001"),
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )
```

**Why a function instead of a module-level variable?**

If you wrote `llm = Anthropic(...)` at the top of the file, the Anthropic client would be instantiated the moment Python imports `agent.py`. That means:
- Tests fail immediately if `ANTHROPIC_API_KEY` isn't set
- You can't swap the LLM in tests by patching

By wrapping it in `_get_llm()`, the client is only created when `run_rag_lookup` is called, and tests can `patch("agents.rag.agent._get_llm")` to return a mock instead.

**Model selection:**
- Default: `claude-haiku-4-5-20251001` — the fastest/cheapest Claude model, appropriate for RAG synthesis where the heavy lifting is retrieval, not reasoning.
- Override: set `RAG_LLM=claude-sonnet-4-6` in your environment for higher quality answers.

**The leading underscore** on `_get_llm` is a Python convention meaning "private to this module" — callers outside this file shouldn't call it directly.

---

### `run_rag_lookup(query, search_fn=None)` — the full pipeline

```python
async def run_rag_lookup(
    query: str,
    search_fn: Callable[[str, int], Awaitable[str]] | None = None,
) -> str:
```

**Signature breakdown:**
- `query: str` — the research question as a plain string
- `search_fn: Callable[[str, int], Awaitable[str]] | None = None` — an optional replacement for the real MCP search. The type annotation says: "a callable that takes a `str` and an `int`, and returns an awaitable that resolves to a `str`". This matches the signature of `search_documents(query, top_k)`.
  - `None` default means: use the real MCP client in production
  - Pass a mock function in tests to avoid needing a live vector DB
- `-> str` — always returns a string, even on error (it returns an early "No relevant documents" string rather than raising)

---

#### Step 1 — Resolve the search function

```python
_search = search_fn or search_documents
```

The `or` operator in Python returns the first truthy value. If `search_fn` was passed (not None, not empty), use it; otherwise fall back to the real `search_documents`. This is the **injectable dependency pattern** — it's what makes the function testable without a live server.

---

#### Step 2 — Retrieve relevant passages

```python
raw_results = await _search(query, top_k=5)
```

Calls the search function (real or mocked) and suspends execution until the MCP server responds. `top_k=5` means: retrieve the 5 most semantically similar chunks to the query. The result is a raw string (JSON-encoded from the MCP server).

---

#### Step 3 — Parse results

```python
try:
    hits = json.loads(raw_results)
except json.JSONDecodeError:
    hits = [{"content": raw_results, "source": "unknown"}]
```

The vector DB returns a JSON string. `json.loads` parses it into a Python list of dicts. The `try/except` handles the case where the MCP server returns something unexpected (plain text, an error message, etc.) — instead of crashing, we treat the raw string itself as a single document chunk with `source: "unknown"`. This is a **graceful degradation** pattern.

---

#### Step 4 — Early exit for empty results

```python
if not hits:
    return "No relevant documents found in the corpus for this query."
```

`not hits` is True when `hits` is an empty list `[]`. If the vector DB found nothing relevant, there's no point calling the LLM — we return immediately with a human-readable message. This saves an API call and avoids the LLM hallucinating an answer from an empty context.

---

#### Step 5 — Build context string

```python
context_parts = []
sources = []
for hit in hits:
    content = hit.get("content", hit.get("text", ""))
    source = hit.get("source", hit.get("id", "unknown"))
    if content:
        context_parts.append(f"[Source: {source}]\n{content}")
        sources.append(source)
```

**Line by line:**

| Line | What it does |
|------|-------------|
| `context_parts = []` | Will hold formatted text blocks, one per retrieved document |
| `sources = []` | Will hold source file names for the citation footer |
| `for hit in hits` | Iterate over each retrieved chunk (each is a dict) |
| `hit.get("content", hit.get("text", ""))` | Try the key `"content"` first; if missing, try `"text"`; if still missing, use empty string. This tolerates different schemas from different vector DB backends. |
| `hit.get("source", hit.get("id", "unknown"))` | Same dual-key fallback for the document identifier |
| `if content:` | Skip chunks with empty content — don't pad the prompt with blank entries |
| `f"[Source: {source}]\n{content}"` | Format each chunk with a labelled header so the LLM can attribute claims to specific documents |

```python
context = "\n\n---\n\n".join(context_parts)
```

Joins all chunks into one multi-section string. The `---` separator makes it visually clear in the prompt where one document ends and another begins, helping the LLM avoid conflating content from different sources.

---

#### Step 6 — Generate the answer

```python
llm = _get_llm()
prompt = (
    f"You are a research assistant. Based ONLY on the following retrieved passages, "
    f"answer the research question. Do not add information not present in the passages.\n\n"
    f"Research question: {query}\n\n"
    f"Retrieved passages:\n{context}\n\n"
    f"Provide a structured answer with:\n"
    f"1. A concise summary (2-3 sentences)\n"
    f"2. Key points from the retrieved documents\n"
    f"3. Source references\n\n"
    f"Answer:"
)
```

**Prompt design choices:**
- `"Based ONLY on the following retrieved passages"` — the critical instruction that prevents the LLM from mixing in its training knowledge. Without this, the model might ignore the retrieved context and hallucinate.
- `"Do not add information not present in the passages"` — reinforces grounding; RAG is only useful if the model actually uses the context.
- Structured output request (summary + key points + references) — makes the response consistently formatted, easier for downstream consumers to parse.
- `f"Answer:"` at the end — a common prompting technique; ending with the start of the expected response nudges the model to begin generating immediately.

```python
response = await llm.acomplete(prompt)
answer_text = str(response)
```

- `llm.acomplete(prompt)` — LlamaIndex's async completion method. It sends the prompt to Anthropic's API and returns a `CompletionResponse` object.
- `str(response)` — converts the response object to a plain string. LlamaIndex's `CompletionResponse.__str__` returns `.text`, the generated answer.

---

#### Step 7 — Append source list

```python
if sources:
    answer_text += f"\n\nSources consulted: {', '.join(set(sources))}"
```

- `set(sources)` — deduplicates source names (the same document could have been retrieved multiple times as different chunks)
- `', '.join(...)` — formats the set as a comma-separated string
- Appended *after* the LLM answer so it doesn't interfere with the generated content

---

## `main.py`

This file wraps the agent logic in an HTTP server that speaks the **A2A protocol**.

### Why A2A?

A2A (Agent-to-Agent) is a protocol that lets agents discover and call each other over HTTP. Instead of direct function calls, agents communicate via:
1. `GET /.well-known/agent.json` — discover what an agent can do
2. `POST /` (JSON-RPC) — send a task and get back a result

This means agents can run on different machines, be written in different languages, and be swapped out without changing the orchestrator.

---

### `_load_card()` — build the AgentCard typed object

```python
def _load_card() -> AgentCard:
    raw = json.loads(_CARD_PATH.read_text())
    url = os.environ.get("RAG_AGENT_URL", raw["url"])
    return AgentCard(
        name=raw["name"],
        description=raw["description"],
        version=raw["version"],
        url=f"{url}/",
        capabilities=AgentCapabilities(...),
        skills=[AgentSkill(...) for s in raw["skills"]],
        ...
    )
```

- Reads `agent_card.json` from disk
- Allows the URL to be overridden via `RAG_AGENT_URL` env var (useful in Docker/Kubernetes where the service URL differs from `localhost`)
- Converts the raw dict into typed Pydantic objects (`AgentCard`, `AgentCapabilities`, `AgentSkill`) so the a2a-sdk can validate and serialize them correctly
- The trailing slash in `f"{url}/"` is required by the a2a-sdk — it expects the base URL to end with `/`

---

### `RagAgentExecutor(AgentExecutor)` — the request handler

```python
class RagAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
```

This class is the bridge between the A2A protocol layer and the agent logic. The a2a-sdk calls `execute()` whenever a new task arrives.

**Parameters:**
- `context: RequestContext` — contains the incoming message and current task state
- `event_queue: EventQueue` — a queue for publishing task lifecycle events (submitted, working, complete, failed)

```python
task = context.current_task or new_task(context.message)
updater = TaskUpdater(event_queue, task.id, task.context_id)
```

- `context.current_task` — if this is a follow-up message in an existing conversation, the task already exists; reuse it
- `new_task(context.message)` — if this is the first message, create a new task object
- `TaskUpdater` — a helper that publishes events to the queue. Callers (e.g., the orchestrator) can subscribe to these events to track progress in real time.

```python
await updater.submit()
await updater.start_work()
```

These two calls publish protocol events:
- `submit()` — signals "task accepted, queued for processing"
- `start_work()` — signals "task is now actively being worked on"

This lets a polling orchestrator know the task moved from `submitted → working` before the actual work begins.

```python
query = ""
if context.message and context.message.parts:
    query = context.message.parts[0].root.text
```

A2A messages are structured as a list of **parts** (to support multi-modal content). Each part has a `.root` (a union type) and `.text`. We only use the first part and treat it as plain text. The nested checks prevent `AttributeError` if the message is malformed.

```python
if not query:
    raise ValueError("No query provided in task message")
```

Guard clause — fail fast with a clear error message rather than passing an empty string to the LLM.

```python
result_text = await run_rag_lookup(query)

await updater.add_artifact(
    [new_agent_text_message(result_text, task.context_id, task.id)]
)
await updater.complete()
```

- `run_rag_lookup(query)` — delegates to the core agent logic
- `add_artifact(...)` — attaches the result to the task as an artifact (a deliverable). Wrapped in `new_agent_text_message` to fit the A2A message schema.
- `complete()` — signals the task is done; the orchestrator can now read the artifact

```python
except Exception as exc:
    error_msg = new_agent_text_message(
        f"RAG lookup failed: {exc}", task.context_id, task.id
    )
    await updater.failed(error_msg)
```

Catches any unhandled exception and reports it as a task failure with a human-readable error message, rather than leaving the task in a "working" state forever.

---

### `cancel()` — handle cancellation requests

```python
async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
    if context.current_task:
        updater = TaskUpdater(...)
        await updater.cancel()
```

If the orchestrator sends a cancel request (e.g., because the user gave up waiting), this method acknowledges it. For the current implementation, we just mark the task as cancelled — we don't interrupt the in-flight `run_rag_lookup` call.

---

### `build_app()` — wire everything together

```python
def build_app():
    agent_card = _load_card()           # 1. Load the agent's identity
    task_store = InMemoryTaskStore()    # 2. Create a task state store
    executor = RagAgentExecutor()       # 3. Create the executor
    handler = DefaultRequestHandler(   # 4. Wire executor + store into a request handler
        agent_executor=executor,
        task_store=task_store,
    )
    return A2AFastAPIApplication(      # 5. Wrap in a FastAPI app
        agent_card=agent_card,
        http_handler=handler,
    ).build()
```

Each component has one responsibility:
- `InMemoryTaskStore` — stores task state (id, status, artifacts) in a Python dict. In production you'd swap this for a Redis-backed store.
- `DefaultRequestHandler` — translates incoming HTTP requests (JSON-RPC) into calls to `executor.execute()` and publishes results back.
- `A2AFastAPIApplication` — creates the FastAPI app, registers the `/.well-known/agent.json` endpoint, and registers the JSON-RPC task endpoint.

```python
app = build_app()
```

Module-level: `app` is instantiated when Python imports `main.py`. This is what ASGI servers like uvicorn look for.

```python
if __name__ == "__main__":
    port = int(os.environ.get("RAG_PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

Runs the server directly if the file is executed as a script. `0.0.0.0` means listen on all network interfaces (required in Docker). In production you'd use `uvicorn agents.rag.main:app --host 0.0.0.0 --port 8002` instead.

---

## Data flow diagram

```
Orchestrator
    │
    │  POST / (JSON-RPC, A2A task)
    ▼
main.py: RagAgentExecutor.execute()
    │
    │  await run_rag_lookup(query)
    ▼
agent.py: run_rag_lookup()
    │
    │  await _search(query, top_k=5)
    ▼
mcp_client.py: search_documents()
    │
    │  HTTP POST to http://localhost:9002
    ▼
vector_db MCP server (Week 1)
    │
    │  JSON array of {content, source} hits
    ▼
agent.py (back in run_rag_lookup)
    │  parse JSON → build context string → build prompt
    │
    │  await llm.acomplete(prompt)
    ▼
Anthropic API (claude-haiku)
    │
    │  synthesised answer text
    ▼
agent.py: append sources → return answer_text
    │
    ▼
main.py: updater.add_artifact() → updater.complete()
    │
    ▼
Orchestrator receives completed task artifact
```

---

## Why each design decision was made

| Decision | Why |
|----------|-----|
| `search_fn=None` injectable parameter | Lets tests pass a mock without a live MCP server |
| `_get_llm()` factory function | Defers Anthropic client creation so `ANTHROPIC_API_KEY` isn't needed at import time; makes LLM patchable in tests |
| `json.loads` with fallback | MCP servers can return errors or plain text; graceful degradation prevents hard crashes |
| Early return on empty hits | Avoids a wasted LLM API call when there's no context to work from |
| `set(sources)` before joining | Prevents duplicate citations when the same document is retrieved as multiple chunks |
| `"Based ONLY on the following retrieved passages"` | The most important RAG prompt instruction — prevents the LLM from ignoring retrieved context |
| `InMemoryTaskStore` | Simple, zero-dependency; sufficient for a single-process server. Swap for Redis in production. |
| `0.0.0.0` bind address | Required to receive connections from outside a container |
