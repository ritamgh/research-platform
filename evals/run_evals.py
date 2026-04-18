"""Run the eval suite against the live research orchestrator.

Usage:
    python evals/run_evals.py
    python evals/run_evals.py --experiment-prefix research-platform --limit 5
    python evals/run_evals.py --metadata stage=baseline prompt=v1
"""
import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# .env lives at the project root, two levels above the worktree
_worktree_root = Path(__file__).parent.parent
load_dotenv(_worktree_root / ".env")
load_dotenv(_worktree_root.parent.parent / ".env")  # project root fallback
from langsmith import Client
from langsmith.evaluation import evaluate

from evals._client import call_research_endpoint, DEFAULT_BASE_URL
from evals.dataset_loader import ensure_langsmith_dataset
from evals.evaluators.faithfulness import faithfulness_evaluator
from evals.evaluators.relevance import relevance_evaluator
from evals.evaluators.citation_accuracy import citation_accuracy_evaluator


def _check_env():
    missing = [v for v in ("LANGSMITH_API_KEY", "OPENAI_API_KEY") if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def _check_orchestrator(base_url: str):
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5.0)
        resp.raise_for_status()
    except Exception as exc:
        print(f"ERROR: Orchestrator not reachable at {base_url}/health — {exc}", file=sys.stderr)
        print("Start the orchestrator first: python -m orchestrator.main", file=sys.stderr)
        sys.exit(1)


def _parse_metadata(pairs: list[str]) -> dict:
    meta = {}
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
            meta[k] = v
    return meta


def main():
    parser = argparse.ArgumentParser(description="Run LangSmith evals against the research orchestrator")
    parser.add_argument("--experiment-prefix", default="research-platform")
    parser.add_argument("--dataset-name", default="research-platform-v1")
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only first N examples (cheap dry run)")
    parser.add_argument("--metadata", nargs="*", default=[], metavar="KEY=VALUE")
    args = parser.parse_args()

    _check_env()
    _check_orchestrator(args.base_url)

    client = Client()
    dataset_name = ensure_langsmith_dataset(client, name=args.dataset_name)

    metadata = _parse_metadata(args.metadata)

    base_url = args.base_url

    def target(inputs: dict) -> dict:
        return call_research_endpoint(inputs["query"], base_url=base_url)

    data: str | list = dataset_name
    if args.limit:
        examples = list(client.list_examples(dataset_name=dataset_name))
        data = examples[: args.limit]
        print(f"Limiting to {len(data)} examples (--limit {args.limit})")

    print(f"\nRunning eval: prefix='{args.experiment_prefix}', dataset='{dataset_name}', concurrency={args.max_concurrency}")
    if metadata:
        print(f"Metadata: {metadata}")

    results = evaluate(
        target,
        data=data,
        evaluators=[faithfulness_evaluator, relevance_evaluator, citation_accuracy_evaluator],
        experiment_prefix=args.experiment_prefix,
        max_concurrency=args.max_concurrency,
        metadata=metadata,
    )

    # Summary table
    scores: dict[str, list[float]] = {}
    for row in results:
        for er in row.get("evaluation_results", {}).get("results", []):
            key = er.key
            if er.score is not None:
                scores.setdefault(key, []).append(er.score)

    print("\n--- Eval Results ---")
    if not scores:
        print("  WARNING: No scores collected. Check that evaluators returned numeric scores.")
        print(f"  Raw first result sample: {next(iter(results), None)}")
    overall = []
    for key, vals in sorted(scores.items()):
        mean = sum(vals) / len(vals)
        overall.append(mean)
        print(f"  {key:<25} {mean:.3f}  (n={len(vals)})")
    if overall:
        print(f"  {'overall':<25} {sum(overall)/len(overall):.3f}")

    print(f"\nExperiment: {results.experiment_name}")
    print("View in LangSmith: https://smith.langchain.com")


if __name__ == "__main__":
    main()
