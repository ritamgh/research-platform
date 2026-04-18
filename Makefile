.PHONY: help run-tools run-agents run-orchestrator run-all stop test test-unit test-integration lint format dev-frontend

CONDA_RUN = conda run -n research-platform
PYTHON    = $(CONDA_RUN) python
PYTEST    = $(CONDA_RUN) pytest

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ─── Services ──────────────────────────────────────────────────────────────────

run-tools:  ## Start all 4 MCP tool servers (ports 9001-9004)
	$(PYTHON) -m mcp_tools.web_search.main &
	$(PYTHON) -m mcp_tools.vector_db.main &
	$(PYTHON) -m mcp_tools.file_reader.main &
	$(PYTHON) -m mcp_tools.citation_checker.main &
	@echo "MCP tool servers started on ports 9001-9004"

run-agents:  ## Start all 3 A2A agent servers (ports 8001-8003)
	$(CONDA_RUN) uvicorn agents.web_research.main:app --port 8001 &
	$(CONDA_RUN) uvicorn agents.rag.main:app --port 8002 &
	$(CONDA_RUN) uvicorn agents.summariser.main:app --port 8003 &
	@echo "A2A agent servers started on ports 8001-8003"

run-orchestrator:  ## Start the orchestrator (port 8000)
	$(PYTHON) -m orchestrator.main

run-all:  ## Start all services (tools + agents + orchestrator)
	$(MAKE) run-tools
	$(MAKE) run-agents
	$(MAKE) run-orchestrator

stop:  ## Kill all running service processes
	@pkill -f "mcp_tools" 2>/dev/null || true
	@pkill -f "agents.web_research" 2>/dev/null || true
	@pkill -f "agents.rag" 2>/dev/null || true
	@pkill -f "agents.summariser" 2>/dev/null || true
	@pkill -f "orchestrator.main" 2>/dev/null || true
	@echo "All services stopped"

# ─── Testing ───────────────────────────────────────────────────────────────────

test:  ## Run all unit tests (excludes integration)
	$(PYTEST) -m "not integration" -v

test-unit:  ## Alias for test
	$(MAKE) test

test-integration:  ## Run integration tests (requires live services + API keys)
	$(PYTEST) -m integration -v

test-tools:  ## Run only MCP tool tests
	$(PYTEST) mcp_tools/ -m "not integration" -v

test-agents:  ## Run only agent tests
	$(PYTEST) agents/ -v

test-orchestrator:  ## Run only orchestrator tests
	$(PYTEST) orchestrator/ -v

test-evals:  ## Run eval unit tests (offline, no API keys needed)
	$(PYTEST) evals/tests/ -v

# ─── Code quality ──────────────────────────────────────────────────────────────

lint:  ## Run ruff linter
	$(CONDA_RUN) ruff check .

format:  ## Auto-format with ruff
	$(CONDA_RUN) ruff format .

# ─── Frontend ──────────────────────────────────────────────────────────────────

dev-frontend:  ## Start frontend dev server (port 5173)
	cd frontend && npm run dev

build-frontend:  ## Build frontend for production
	cd frontend && npm run build
