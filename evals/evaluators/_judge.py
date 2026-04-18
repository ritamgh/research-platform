"""Shared OpenAI LLM-as-judge helper."""
import json
import re

from openai import OpenAI

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def judge(
    system: str,
    user: str,
    *,
    model: str = "gpt-4o-mini",
    max_tokens: int = 300,
    client: OpenAI | None = None,
) -> dict:
    """Call the LLM judge. Returns {"score": float, "reasoning": str}.

    On any failure (API error, parse error) returns score=0.0 with error reasoning
    so a single bad call never crashes the entire eval run.
    """
    oai = client or _get_client()
    try:
        completion = oai.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = completion.choices[0].message.content or ""
        return _parse(raw)
    except Exception as exc:
        return {"score": 0.0, "reasoning": f"judge_error: {exc}"}


def _parse(raw: str) -> dict:
    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip()

    # Find JSON object in the response
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            score = float(data.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            reasoning = str(data.get("reasoning", data.get("reason", "")))
            return {"score": score, "reasoning": reasoning}
        except (json.JSONDecodeError, ValueError):
            pass

    return {"score": 0.0, "reasoning": f"parse_error: {raw[:200]}"}
