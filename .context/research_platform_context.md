# Multi-Agent Research & Evaluation Platform
## Project Context for Claude Code

---

## Project Overview

A production-grade multi-agent research platform where specialized agents collaborate to answer deep research questions. The system teaches three core modern AI engineering skills in one project:

- **MCP (Model Context Protocol)** — standardized tool exposure and consumption
- **A2A (Agent2Agent Protocol)** — cross-framework agent interoperability
- **LangSmith Evals** — automated quality measurement and regression tracking

A user submits a research question. The LangGraph orchestrator routes it to specialized remote agents via A2A. Each agent uses MCP tool servers to do its job. LangSmith traces and evaluates every run automatically.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Query                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│              Orchestrator Agent (LangGraph)                      │
│         StateGraph + LangSmith tracing throughout               │
└────────────┬────────────────────┬──────────────────┬────────────┘
             │    A2A Protocol    │                  │
             ▼                   ▼                  ▼
┌────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│  Web Research Agent│ │    RAG Agent     │ │  Summariser Agent    │
│  (CrewAI)          │ │  (LlamaIndex)    │ │  (Anthropic SDK)     │
│  A2A server        │ │  A2A server      │ │  A2A server          │
└────────┬───────────┘ └───────┬──────────┘ └──────────────────────┘
         │ MCP                 │ MCP
         ▼                     ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐
│ Web Search  │   │  Vector DB  │   │ File Reader │   │ Citation Checker │
│  MCP tool   │   │  MCP tool   │   │  MCP tool   │   │    MCP tool      │
└─────────────┘   └─────────────┘   └─────────────┘   └──────────────────┘
             │                  │                  │
             └──────────────────┴──────────────────┘
                                 │ traces + eval data (dashed)
                    ┌────────────▼──────────────────┐
                    │   LangSmith Eval Pipeline      │
                    │  Faithfulness · Relevance ·    │
                    │     Citation accuracy          │
                    └───────────────────────────────┘
```

**Key relationships:**
- Orchestrator → Agents: A2A protocol (HTTP/JSON-RPC, Agent Cards)
- Agents → Tools: MCP protocol (standardized tool servers)
- Everything → LangSmith: traces, eval datasets, custom evaluators

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Orchestrator | LangGraph | StateGraph with conditional routing |
| Agent 1 | CrewAI | Web research (deliberate cross-framework choice) |
| Agent 2 | LlamaIndex | RAG over local document corpus |
| Agent 3 | Anthropic SDK | Final synthesis and summarization |
| Agent protocol | A2A (Python SDK) | Cross-agent communication |
| Tool protocol | MCP (Python SDK) | Standardized tool exposure |
| Observability | LangSmith | Tracing, eval datasets, custom evaluators |
| Search tool | Tavily API | Web search MCP server |
| Vector DB | FAISS / Supabase | RAG MCP server |
| API framework | FastAPI + async | Serving all agent endpoints |
| Containers | Docker | Each agent/tool as isolated service |

---

## Project Structure

```
research-platform/
├── orchestrator/
│   ├── main.py                  # LangGraph StateGraph definition
│   ├── state.py                 # Shared state schema (Pydantic)
│   ├── nodes/
│   │   ├── router.py            # Classifies query → which agents to call
│   │   ├── delegate.py          # A2A client calls to remote agents
│   │   ├── synthesize.py        # Merges agent results into final answer
│   │   └── evaluate.py          # Triggers LangSmith eval on completion
│   └── a2a_client.py            # A2A client wrapper
│
├── agents/
│   ├── web_research/
│   │   ├── main.py              # FastAPI app + A2A server endpoint
│   │   ├── agent.py             # CrewAI agent definition
│   │   ├── agent_card.json      # A2A Agent Card (capabilities manifest)
│   │   └── mcp_client.py        # Connects to web_search MCP tool
│   │
│   ├── rag/
│   │   ├── main.py              # FastAPI app + A2A server endpoint
│   │   ├── agent.py             # LlamaIndex agent definition
│   │   ├── agent_card.json      # A2A Agent Card
│   │   └── mcp_client.py        # Connects to vector_db + file_reader MCP tools
│   │
│   └── summariser/
│       ├── main.py              # FastAPI app + A2A server endpoint
│       ├── agent.py             # Anthropic SDK agent
│       ├── agent_card.json      # A2A Agent Card
│       └── mcp_client.py        # Connects to citation_checker MCP tool
│
├── mcp_tools/
│   ├── web_search/
│   │   ├── server.py            # MCP server wrapping Tavily API
│   │   └── main.py              # FastAPI entrypoint
│   │
│   ├── vector_db/
│   │   ├── server.py            # MCP server wrapping FAISS/Supabase
│   │   ├── ingest.py            # Document ingestion pipeline
│   │   └── main.py
│   │
│   ├── file_reader/
│   │   ├── server.py            # MCP server for PDF/text parsing
│   │   └── main.py
│   │
│   └── citation_checker/
│       ├── server.py            # MCP server: validates URLs + source credibility
│       └── main.py
│
├── evals/
│   ├── dataset.json             # 30 research questions + reference answers
│   ├── evaluators/
│   │   ├── faithfulness.py      # LLM-as-judge: answer grounded in context?
│   │   ├── relevance.py         # LLM-as-judge: answer addresses question?
│   │   └── citation_accuracy.py # Regex + LLM: sources real and cited correctly?
│   ├── run_evals.py             # Runs full eval suite against LangSmith dataset
│   └── report.py                # Generates eval summary report
│
├── docker-compose.yml           # Orchestrates all services
├── .env.example
└── README.md
```

---

## Core Concepts to Implement

### 1. MCP Tool Servers

Each MCP tool is an independent FastAPI service that implements the MCP server protocol. Agents connect to them as MCP clients.

**MCP server pattern (web_search example):**
```python
# mcp_tools/web_search/server.py
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent
import mcp.server.stdio

server = Server("web-search-tool")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_web",
            description="Search the web for recent information on a topic",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "search_web":
        # Call Tavily API here
        results = await tavily_search(arguments["query"], arguments.get("num_results", 5))
        return [TextContent(type="text", text=str(results))]
```

**Key MCP concepts to understand:**
- `list_tools()` — advertises what this server can do (like an API schema)
- `call_tool()` — executes the tool when an agent requests it
- Tools are discovered dynamically — agents don't hardcode tool schemas
- Each MCP server runs as its own process/service

---

### 2. A2A Agent Cards and Server Endpoints

Every agent publishes an Agent Card at `/.well-known/agent.json` describing its capabilities. The orchestrator discovers agents by fetching these cards.

**Agent Card structure:**
```json
{
  "name": "web-research-agent",
  "description": "Searches the web for recent information and returns structured findings",
  "version": "1.0.0",
  "url": "http://web-research-agent:8001",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "web_research",
      "name": "Web research",
      "description": "Given a research question, searches the web and returns summarized findings with sources",
      "inputModes": ["text"],
      "outputModes": ["text"]
    }
  ],
  "authentication": {
    "schemes": ["bearer"]
  }
}
```

**A2A server endpoint pattern:**
```python
# agents/web_research/main.py
from fastapi import FastAPI
from a2a.server import A2AServer
from a2a.types import Task, TaskResult

app = FastAPI()
a2a = A2AServer(app)

@app.get("/.well-known/agent.json")
async def agent_card():
    return load_agent_card()  # returns agent_card.json contents

@a2a.on_task()
async def handle_task(task: Task) -> TaskResult:
    query = task.message.content
    # Run the CrewAI agent with this query
    result = await run_web_research_agent(query)
    return TaskResult(
        task_id=task.id,
        status="completed",
        artifacts=[{"type": "text", "content": result}]
    )
```

**A2A client (in orchestrator):**
```python
# orchestrator/a2a_client.py
from a2a.client import A2AClient

async def call_agent(agent_url: str, query: str) -> str:
    async with A2AClient(agent_url) as client:
        # Discover capabilities from Agent Card
        card = await client.get_agent_card()
        
        # Send task
        task = await client.send_task(
            message={"role": "user", "content": query}
        )
        
        # Poll for result (or stream)
        result = await client.wait_for_completion(task.id)
        return result.artifacts[0]["content"]
```

---

### 3. LangGraph Orchestrator State

```python
# orchestrator/state.py
from pydantic import BaseModel
from typing import Optional, List

class ResearchState(BaseModel):
    # Input
    query: str
    
    # Routing decision
    needs_web_search: bool = False
    needs_rag: bool = False
    
    # Agent results
    web_research_result: Optional[str] = None
    rag_result: Optional[str] = None
    
    # Final output
    final_answer: Optional[str] = None
    sources: List[str] = []
    
    # Eval metadata
    retrieved_context: List[str] = []  # for faithfulness eval
    run_id: Optional[str] = None       # LangSmith run ID
```

**LangGraph graph definition:**
```python
# orchestrator/main.py
from langgraph.graph import StateGraph, END
from langsmith import traceable

def build_graph():
    graph = StateGraph(ResearchState)
    
    graph.add_node("router", router_node)
    graph.add_node("web_research", web_research_node)
    graph.add_node("rag_lookup", rag_node)
    graph.add_node("synthesize", synthesize_node)
    
    graph.set_entry_point("router")
    
    graph.add_conditional_edges("router", route_decision, {
        "web_only": "web_research",
        "rag_only": "rag_lookup",
        "both": "web_research",   # web_research → rag_lookup in sequence
        "neither": "synthesize"
    })
    
    graph.add_edge("web_research", "rag_lookup")
    graph.add_edge("rag_lookup", "synthesize")
    graph.add_edge("synthesize", END)
    
    return graph.compile()
```

---

### 4. LangSmith Eval Pipeline

This is the most important part to get right. Three custom evaluators:

**Faithfulness evaluator:**
```python
# evals/evaluators/faithfulness.py
from langsmith.evaluation import run_evaluator
from anthropic import Anthropic

client = Anthropic()

@run_evaluator
def faithfulness_evaluator(run, example):
    """
    Checks: does the answer contain ONLY claims supported by retrieved context?
    Score 0-1. Penalizes hallucinated facts not in the context.
    """
    answer = run.outputs["final_answer"]
    context = run.outputs["retrieved_context"]
    
    prompt = f"""You are evaluating whether an AI answer is faithful to its source context.

Context retrieved:
{chr(10).join(context)}

Answer given:
{answer}

Score from 0 to 1:
- 1.0: Every claim in the answer is directly supported by the context
- 0.5: Most claims supported, minor unsupported additions
- 0.0: Answer contains significant claims not in the context (hallucination)

Respond with JSON: {{"score": float, "reason": "brief explanation"}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    
    result = json.loads(response.content[0].text)
    return {"key": "faithfulness", "score": result["score"], "comment": result["reason"]}
```

**Running evals:**
```python
# evals/run_evals.py
from langsmith import Client
from langsmith.evaluation import evaluate

ls_client = Client()

def run_full_eval():
    # Load your dataset of 30 research questions
    dataset = ls_client.read_dataset(dataset_name="research-platform-eval-v1")
    
    # Run the full pipeline against each example
    results = evaluate(
        lambda inputs: run_research_pipeline(inputs["query"]),
        data=dataset,
        evaluators=[
            faithfulness_evaluator,
            relevance_evaluator,
            citation_accuracy_evaluator
        ],
        experiment_prefix="research-platform",
        metadata={"version": "1.0", "model": "claude-sonnet-4"}
    )
    
    print(f"Faithfulness: {results.aggregate_metrics['faithfulness']:.2f}")
    print(f"Relevance: {results.aggregate_metrics['relevance']:.2f}")
    print(f"Citation accuracy: {results.aggregate_metrics['citation_accuracy']:.2f}")
```

**Dataset format (evals/dataset.json):**
```json
[
  {
    "inputs": {
      "query": "What are the main approaches to mechanistic interpretability in large language models?"
    },
    "outputs": {
      "reference_answer": "Key approaches include activation patching, sparse autoencoders for feature extraction, circuit analysis tracing specific capabilities, and probing classifiers. Recent work by Anthropic and others has focused on identifying monosemantic features via dictionary learning.",
      "required_topics": ["activation patching", "sparse autoencoders", "circuit analysis"],
      "min_sources": 2
    }
  }
]
```

---

## Build Order (6 Weeks)

### Week 1 — MCP Tool Servers ✅
**Goal:** All 4 MCP tool servers running and testable in isolation.

Tasks:
- [x] Build `web_search` MCP server (wrap Tavily API)
- [x] Build `vector_db` MCP server (FAISS + document ingestion pipeline)
- [x] Build `file_reader` MCP server (PyMuPDF for PDFs)
- [x] Build `citation_checker` MCP server (URL validation + credibility heuristics)
- [x] Write unit tests for each tool server

**Key learning:** You're writing MCP *servers*, not just consuming tools. Understand the server/client contract.

---

### Week 2 — Individual A2A Agents
**Goal:** All 3 agents running as independent A2A servers, testable in isolation.

Tasks:
- [ ] Build `web_research` agent (CrewAI) with MCP client connecting to `web_search` tool
- [ ] Write its `agent_card.json` and expose `/.well-known/agent.json`
- [ ] Build `rag` agent (LlamaIndex) with MCP client connecting to `vector_db` + `file_reader`
- [ ] Build `summariser` agent (Anthropic SDK) with MCP client connecting to `citation_checker`
- [ ] Test each agent: POST a task directly to its A2A endpoint, verify the result artifact
- [ ] Verify Agent Cards are valid and discoverable

**Key learning:** You're writing A2A *servers*. Each agent is independently deployable and framework-agnostic from the outside.

---

### Week 3 — LangGraph Orchestrator + Integration
**Goal:** Full end-to-end pipeline working.

Tasks:
- [ ] Define `ResearchState` Pydantic schema
- [ ] Build router node (LLM classifies query into routing decision)
- [ ] Build delegate nodes (A2A client calls to each remote agent)
- [ ] Build synthesize node (merges web + RAG results via Anthropic SDK)
- [ ] Wire conditional edges in StateGraph
- [ ] Add LangSmith tracing with `@traceable` throughout
- [ ] Log `retrieved_context` to state for eval pipeline
- [ ] Test full pipeline end-to-end with 5 sample queries
- [ ] Verify traces appear in LangSmith dashboard

**Key learning:** The orchestrator doesn't know or care how agents are implemented — it only speaks A2A.

---

### Week 4 — Google ADK Integration
**Goal:** Introduce ADK as a layer that abstracts the A2A boilerplate from Weeks 2–3 and replaces the LangGraph orchestrator with an ADK-native one. The agents stay the same; the wiring changes.

ADK provides native A2A protocol support and a multi-agent orchestration model, so you stop writing Agent Cards, task lifecycle management, and JSON-RPC transport by hand.

Tasks:
- [ ] Install and configure `google-adk` alongside existing dependencies
- [ ] Refactor `web_research`, `rag`, and `summariser` agents to use ADK's A2A server abstractions (remove raw `a2a-python` boilerplate)
- [ ] Rebuild the orchestrator as an ADK multi-agent (replacing the LangGraph StateGraph + router/delegate/synthesize nodes)
- [ ] Verify routing, parallel delegation, and synthesis still work correctly end-to-end
- [ ] Preserve LangSmith tracing through the ADK orchestrator
- [ ] Run the same 5 sample queries from Week 3 and confirm identical results
- [ ] Delete the now-redundant LangGraph orchestrator code

**Key learning:** You built the LangGraph version first so you know exactly what ADK is abstracting. This week is about understanding the tradeoff — when the abstraction helps and what it hides.

---

### Week 5 — LangSmith Eval Pipeline
**Goal:** Automated eval running against a proper dataset with regression tracking.

Tasks:
- [ ] Build eval dataset: 30 research questions with reference answers in LangSmith
- [ ] Write `faithfulness_evaluator` (LLM-as-judge)
- [ ] Write `relevance_evaluator` (LLM-as-judge)
- [ ] Write `citation_accuracy_evaluator` (regex + LLM)
- [ ] Run first baseline eval, record scores
- [ ] Intentionally degrade one prompt, run eval, verify scores drop
- [ ] Restore and improve the prompt, run eval, verify scores improve
- [ ] Set up `run_evals.py` as a script that can be run in CI
- [ ] Write `report.py` that prints a summary comparison between two experiment runs

**Key learning:** The eval loop IS the engineering discipline. Prompt changes without evals are guesses.

---

### Week 6 — Docker Compose + Deployment
**Goal:** Full platform runnable with a single `docker-compose up`.

Tasks:
- [ ] Write `Dockerfile` for each MCP tool server
- [ ] Write `Dockerfile` for each A2A agent
- [ ] Write `Dockerfile` for the ADK orchestrator
- [ ] Wire all services in `docker-compose.yml` with correct `depends_on` and port mappings
- [ ] Add health checks so agents wait for their MCP tools to be ready
- [ ] Test `docker-compose up` end-to-end from cold start
- [ ] Write `.env.example` with all required environment variables

**Key learning:** Containerization is the final step — get everything working locally first, then wrap in Docker.

---

## Environment Variables

```bash
# .env.example

# LLM APIs
ANTHROPIC_API_KEY=
OPENAI_API_KEY=           # for some LangSmith evaluators

# Search
TAVILY_API_KEY=

# LangSmith
LANGCHAIN_API_KEY=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=research-platform

# Vector DB (if using Supabase instead of local FAISS)
SUPABASE_URL=
SUPABASE_KEY=

# A2A agent URLs (used by orchestrator)
WEB_RESEARCH_AGENT_URL=http://localhost:8001
RAG_AGENT_URL=http://localhost:8002
SUMMARISER_AGENT_URL=http://localhost:8003

# MCP tool URLs (used by agents)
WEB_SEARCH_MCP_URL=http://localhost:9001
VECTOR_DB_MCP_URL=http://localhost:9002
FILE_READER_MCP_URL=http://localhost:9003
CITATION_CHECKER_MCP_URL=http://localhost:9004
```

---

## Docker Compose Skeleton

```yaml
# docker-compose.yml
version: "3.9"
services:

  # MCP Tool Servers (port 9xxx)
  mcp-web-search:
    build: ./mcp_tools/web_search
    ports: ["9001:9001"]
    env_file: .env

  mcp-vector-db:
    build: ./mcp_tools/vector_db
    ports: ["9002:9002"]
    volumes: ["./data/corpus:/data/corpus"]
    env_file: .env

  mcp-file-reader:
    build: ./mcp_tools/file_reader
    ports: ["9003:9003"]
    volumes: ["./data/uploads:/data/uploads"]

  mcp-citation-checker:
    build: ./mcp_tools/citation_checker
    ports: ["9004:9004"]

  # A2A Agent Servers (port 8xxx)
  agent-web-research:
    build: ./agents/web_research
    ports: ["8001:8001"]
    env_file: .env
    depends_on: [mcp-web-search]

  agent-rag:
    build: ./agents/rag
    ports: ["8002:8002"]
    env_file: .env
    depends_on: [mcp-vector-db, mcp-file-reader]

  agent-summariser:
    build: ./agents/summariser
    ports: ["8003:8003"]
    env_file: .env
    depends_on: [mcp-citation-checker]

  # Orchestrator
  orchestrator:
    build: ./orchestrator
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [agent-web-research, agent-rag, agent-summariser]
```

---

## Key Dependencies

```txt
# requirements.txt (shared base)
langchain>=0.3
langgraph>=0.2
langsmith>=0.1
anthropic>=0.40
crewai>=0.80
llama-index>=0.12
a2a-python>=0.3           # A2A Python SDK
mcp>=1.0                  # MCP Python SDK
fastapi>=0.115
uvicorn>=0.30
pydantic>=2.0
faiss-cpu>=1.8
pymupdf>=1.24             # PDF parsing
tavily-python>=0.5
httpx>=0.27               # async HTTP client
python-dotenv>=1.0
```

---

## Things That Will Trip You Up (Save This)

**MCP:**
- The MCP server runs as a subprocess communicating over stdio by default — for HTTP-based deployment you need `mcp.server.fastmcp` or a custom transport layer. Decide upfront which transport you're using.
- `list_tools()` is called fresh on every agent startup. If your MCP server is down when the agent starts, the agent has no tools. Add health checks.

**A2A:**
- Agent Cards must be served at exactly `/.well-known/agent.json` — the path is part of the spec.
- A2A is still at v0.3 as of early 2026. The Python SDK API can change between minor versions. Pin your version.
- Task lifecycle states are: `submitted → working → completed / failed`. Your orchestrator must handle the `failed` state gracefully.

**LangSmith Evals:**
- `run.outputs` only contains what your pipeline explicitly returns. If you forget to include `retrieved_context` in your LangGraph state output, the faithfulness evaluator has nothing to judge against.
- LLM-as-judge evaluators cost tokens on every eval run. Keep your dataset at 20-30 examples during development; scale up for final benchmarking.
- Experiment names are immutable once created. Use a versioning convention like `research-platform-v1-baseline` from the start.

**LangGraph + A2A together:**
- A2A calls are async and can take 10-30 seconds. Use `asyncio.gather()` in your delegate node to call web_research and rag agents in parallel when both are needed.
- LangSmith traces the orchestrator but not the internals of remote agents (they're separate services). To get full traces, initialize LangSmith in each agent service too and pass the parent `run_id` through the A2A task metadata.

---

## Success Criteria

By the end of the project you should be able to:

1. Run `docker-compose up` and have the entire platform start correctly
2. POST a research question to `http://localhost:8000/research` and get a cited answer back
3. Open LangSmith and see the full trace: router decision → which agents were called → synthesized result
4. Run `python evals/run_evals.py` and see three eval scores printed
5. Change a prompt in one agent, re-run evals, and observe the score change
6. Explain to an interviewer: why A2A instead of direct HTTP calls, why MCP instead of hardcoded tools, and what your LangSmith evaluators actually measure

---

## Interview Talking Points This Project Gives You

- **"How would you make agents from different frameworks interoperate?"** → A2A Agent Cards, HTTP/JSON-RPC transport, framework-agnostic task/artifact model
- **"How do you standardize tool access across agents?"** → MCP servers, `list_tools()` discovery, each agent connects as MCP client
- **"How do you know if a prompt change improved quality?"** → LangSmith eval dataset, LLM-as-judge evaluators, experiment comparison
- **"How do you handle latency in multi-agent systems?"** → Parallel A2A calls with `asyncio.gather()`, timeout handling, task state polling
- **"How do you debug when something goes wrong?"** → LangSmith trace shows every node, every agent call, every tool invocation with inputs/outputs

---

*This document is the source of truth for Claude Code. Reference the architecture diagram, build in the specified order, and implement each component exactly as described before moving to the next week.*
