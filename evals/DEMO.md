# Week 5 Demo: Baseline → Degrade → Recover

This runbook demonstrates that the eval pipeline detects prompt quality changes.

## Prerequisites

All services running:
```bash
# MCP tools
conda run -n research-platform python -m mcp_tools.web_search.main &
conda run -n research-platform python -m mcp_tools.vector_db.main &
conda run -n research-platform python -m mcp_tools.file_reader.main &
conda run -n research-platform python -m mcp_tools.citation_checker.main &

# ADK agents
conda run -n research-platform uvicorn agents.web_research.main:app --port 8001 &
conda run -n research-platform uvicorn agents.rag.main:app --port 8002 &
conda run -n research-platform uvicorn agents.summariser.main:app --port 8003 &

# Orchestrator
conda run -n research-platform python -m orchestrator.main &
```

---

## Step 1 — Baseline

Run the eval with the default coordinator prompt:
```bash
conda run -n research-platform python evals/run_evals.py \
  --metadata stage=baseline prompt=v1
```

Record the experiment name printed at the end (e.g. `research-platform-abc123`).

Expected scores: faithfulness ~0.80, relevance ~0.80, citation_accuracy ~0.65

---

## Step 2 — Degrade

Edit `orchestrator/coordinator.py` — replace `COORDINATOR_INSTRUCTION` with:

```python
COORDINATOR_INSTRUCTION = (
    "You are a research assistant. Answer all questions directly from your own knowledge. "
    "Do not delegate to any sub-agents. Do not cite sources."
)
```

Restart the orchestrator, then run:
```bash
conda run -n research-platform python evals/run_evals.py \
  --metadata stage=degraded prompt=degraded
```

Record this experiment name.

Expected: faithfulness drops (no retrieved context → answers unsupported),
citation_accuracy drops sharply (model told not to cite).

---

## Step 3 — Compare Baseline vs Degraded

```bash
conda run -n research-platform python evals/report.py \
  research-platform-<baseline-id> research-platform-<degraded-id>
```

You should see WARN flags on faithfulness and citation_accuracy.

---

## Step 4 — Recover

Restore the original `COORDINATOR_INSTRUCTION` in `orchestrator/coordinator.py`
(revert your change). Optionally strengthen it by adding:
```
Always cite sources using [1], [2] style markers when using retrieved information.
```

Restart orchestrator, run:
```bash
conda run -n research-platform python evals/run_evals.py \
  --metadata stage=recovered prompt=v2
```

---

## Step 5 — Final Comparison

```bash
conda run -n research-platform python evals/report.py \
  research-platform-<baseline-id> research-platform-<recovered-id>
```

Expected: all metrics at or above baseline, no WARN flags.

---

## Cheap Dry Run (no real LLM spend)

Use `--limit 3` to run against only 3 examples during development:
```bash
conda run -n research-platform python evals/run_evals.py --limit 3
```
