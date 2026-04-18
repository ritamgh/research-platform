"""Compare two LangSmith experiment runs and print a delta table.

Usage:
    python evals/report.py <experiment_a> <experiment_b>
    python evals/report.py research-platform-baseline research-platform-degraded --verbose
"""
import argparse
import os
import sys

from langsmith import Client

REGRESSION_THRESHOLD = 0.05


def _fetch_scores(client: Client, experiment_name: str) -> dict[str, list[float]]:
    """Return {metric_key: [scores]} for a given experiment (project name)."""
    try:
        runs = list(client.list_runs(project_name=experiment_name, execution_order=1))
    except Exception as exc:
        print(f"ERROR: Could not fetch runs for '{experiment_name}': {exc}", file=sys.stderr)
        sys.exit(1)

    if not runs:
        print(f"WARNING: No runs found for experiment '{experiment_name}'", file=sys.stderr)
        return {}

    run_ids = [r.id for r in runs]
    scores: dict[str, list[float]] = {}

    for feedback in client.list_feedback(run_ids=run_ids):
        key = feedback.key
        if feedback.score is not None:
            scores.setdefault(key, []).append(float(feedback.score))

    return scores


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def _flag(delta: float) -> str:
    if abs(delta) < REGRESSION_THRESHOLD:
        return "OK"
    return "WARN" if delta < 0 else "IMPROVED"


def main():
    parser = argparse.ArgumentParser(description="Compare two LangSmith experiment runs")
    parser.add_argument("experiment_a", help="Baseline experiment name")
    parser.add_argument("experiment_b", help="Comparison experiment name")
    parser.add_argument("--verbose", action="store_true", help="Show per-example score breakdown")
    args = parser.parse_args()

    if not os.environ.get("LANGSMITH_API_KEY"):
        print("ERROR: LANGSMITH_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = Client()

    print(f"\nFetching '{args.experiment_a}'...")
    scores_a = _fetch_scores(client, args.experiment_a)
    print(f"Fetching '{args.experiment_b}'...")
    scores_b = _fetch_scores(client, args.experiment_b)

    all_keys = sorted(set(scores_a) | set(scores_b))
    if not all_keys:
        print("No eval metrics found for either experiment.")
        sys.exit(1)

    print(f"\n{'Metric':<28} {'A':>7} {'B':>7} {'Delta':>8}  Status")
    print("-" * 60)

    overall_a, overall_b = [], []
    for key in all_keys:
        a = _mean(scores_a.get(key, []))
        b = _mean(scores_b.get(key, []))
        delta = b - a
        flag = _flag(delta)
        overall_a.append(a)
        overall_b.append(b)
        delta_str = f"{delta:+.3f}" if delta == delta else "   n/a"
        print(f"  {key:<26} {a:>7.3f} {b:>7.3f} {delta_str:>8}  {flag}")

    if overall_a and overall_b:
        oa = sum(overall_a) / len(overall_a)
        ob = sum(overall_b) / len(overall_b)
        d = ob - oa
        print("-" * 60)
        print(f"  {'overall':<26} {oa:>7.3f} {ob:>7.3f} {d:+.3f}  {_flag(d)}")

    print(f"\nA: {args.experiment_a}")
    print(f"B: {args.experiment_b}")
    print(f"Regression threshold: {REGRESSION_THRESHOLD} (delta < -{REGRESSION_THRESHOLD} → WARN)")


if __name__ == "__main__":
    main()
