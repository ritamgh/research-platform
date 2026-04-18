"""Relevance evaluator: does the answer address the query?"""
from evals.evaluators._judge import judge

_SYSTEM = """You are an expert evaluator assessing whether an AI answer is relevant and directly addresses the user's question.

Score from 0 to 1:
- 1.0: Answer directly and completely addresses the question
- 0.7: Answer mostly addresses the question with minor gaps
- 0.3: Answer is tangentially related but misses the core question
- 0.0: Answer is off-topic or does not address the question

Respond with ONLY valid JSON: {"score": <float 0-1>, "reasoning": "<one sentence>"}"""


def relevance_evaluator(run, example) -> dict:
    error = (run.outputs or {}).get("error")
    if error:
        return {"key": "relevance", "score": None, "comment": f"skipped: {error}"}

    answer = (run.outputs or {}).get("answer", "")
    query = (example.inputs or {}).get("query", "")
    required_topics: list[str] = (example.outputs or {}).get("required_topics", [])

    if not answer:
        return {"key": "relevance", "score": 0.0, "comment": "empty answer"}

    user = f"Question: {query}\n\nAnswer: {answer}"
    result = judge(_SYSTEM, user)
    llm_score = result["score"]

    # Topic coverage: fraction of required_topics found in answer (case-insensitive)
    if required_topics:
        answer_lower = answer.lower()
        hits = sum(1 for t in required_topics if t.lower() in answer_lower)
        topic_score = hits / len(required_topics)
        final_score = round(0.7 * llm_score + 0.3 * topic_score, 4)
    else:
        final_score = llm_score

    return {"key": "relevance", "score": final_score, "comment": result["reasoning"]}
