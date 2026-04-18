"""Citation accuracy evaluator: does the answer cite sources appropriately?"""
import re

from evals.evaluators._judge import judge

# Patterns that indicate a citation in the answer text
_CITATION_PATTERNS = [
    r"\[\d+\]",                        # [1], [2]
    r"https?://\S+",                   # bare URLs
    r"\(source:[^)]+\)",               # (source: ...)
    r"according to [^\.,]{3,40}",      # "according to ..."
    r"per [A-Z][^\.,]{2,30}",          # "per Reuters"
    r"reported by [^\.,]{3,30}",       # "reported by ..."
]
_CITATION_RE = re.compile("|".join(_CITATION_PATTERNS), re.IGNORECASE)

_SYSTEM = """You are evaluating whether citations or source references in an AI answer are integrated naturally and appropriately.

Score from 0 to 1:
- 1.0: Citations are specific, well-integrated, and support key claims
- 0.7: Some citations present but coverage is incomplete
- 0.3: Citations are vague or only mentioned superficially
- 0.0: No meaningful citation despite claims requiring sources

Respond with ONLY valid JSON: {"score": <float 0-1>, "reasoning": "<one sentence>"}"""


def citation_accuracy_evaluator(run, example) -> dict:
    error = (run.outputs or {}).get("error")
    if error:
        return {"key": "citation_accuracy", "score": None, "comment": f"skipped: {error}"}

    answer = (run.outputs or {}).get("answer", "")
    min_sources: int = (example.outputs or {}).get("min_sources", 0)

    # Direct-route questions need no citations
    if min_sources == 0:
        return {"key": "citation_accuracy", "score": 1.0, "comment": "direct-answer-skip: no sources expected"}

    if not answer:
        return {"key": "citation_accuracy", "score": 0.0, "comment": "empty answer"}

    citations = _CITATION_RE.findall(answer)
    cited_count = len(set(citations))
    count_score = min(cited_count / min_sources, 1.0)

    user = f"Answer (check for citation quality):\n{answer}"
    result = judge(_SYSTEM, user)

    final_score = round(0.5 * count_score + 0.5 * result["score"], 4)
    return {"key": "citation_accuracy", "score": final_score, "comment": result["reasoning"]}
