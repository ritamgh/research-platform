"""Faithfulness evaluator: is every claim in the answer grounded in retrieved context?"""
from evals.evaluators._judge import judge

_SYSTEM = """You are an expert evaluator assessing whether an AI answer is faithful to its source context.

Score the answer from 0 to 1:
- 1.0: Every factual claim in the answer is directly supported by the context
- 0.7: Minor unsupported elaboration but no contradictions with context
- 0.3: Several claims are unsupported or partially contradicted
- 0.0: Answer fabricates content not present in the context (hallucination)

Respond with ONLY valid JSON: {"score": <float 0-1>, "reasoning": "<one sentence>"}"""


def faithfulness_evaluator(run, example) -> dict:
    # Infrastructure errors — exclude from quality aggregates
    error = (run.outputs or {}).get("error")
    if error:
        return {"key": "faithfulness", "score": None, "comment": f"skipped: {error}"}

    answer = (run.outputs or {}).get("answer", "")
    context: list[str] = (run.outputs or {}).get("retrieved_context", [])
    route_type = (example.metadata or {}).get("route_type", "unknown")

    if not answer:
        return {"key": "faithfulness", "score": 0.0, "comment": "empty answer"}

    if not context:
        if route_type == "direct":
            # Direct questions have no retrieval — faithfulness is N/A
            return {"key": "faithfulness", "score": 1.0, "comment": "direct-answer-skip: no retrieval expected"}
        # Non-direct question with no context = retrieval failure
        return {
            "key": "faithfulness",
            "score": 0.0,
            "comment": f"retrieval_failure: route_type={route_type} but no context collected",
        }

    context_text = "\n---\n".join(context)
    user = f"Context:\n{context_text}\n\nAnswer:\n{answer}"

    result = judge(_SYSTEM, user)
    return {"key": "faithfulness", "score": result["score"], "comment": result["reasoning"]}
