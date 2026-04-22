"""Summariser agent using OpenAI SDK + citation_checker MCP tool."""
import asyncio
import json
import os
import re
from typing import Callable, Awaitable

from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from agents.summariser.mcp_client import check_credibility


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = wrap_openai(AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "")))
    return _client


def _extract_urls(text: str) -> list[str]:
    """Extract all URLs from a text string."""
    url_pattern = re.compile(
        r"https?://[^\s\)\]\",<>]+"
    )
    return list(set(url_pattern.findall(text)))


@traceable(name="summariser", run_type="chain", tags=["agent"])
async def run_summariser(
    query: str,
    web_findings: str = "",
    rag_findings: str = "",
    credibility_fn: Callable[[str], Awaitable[str]] | None = None,
) -> str:
    """Synthesise web and RAG findings into a final cited answer.

    1. Extract URLs from both findings
    2. Check credibility of each URL via citation_checker MCP
    3. Use OpenAI SDK to write the final synthesis, filtering low-credibility sources
    """
    _check = credibility_fn or check_credibility

    # Collect all URLs from the findings
    all_text = f"{web_findings}\n{rag_findings}"
    urls = _extract_urls(all_text)

    # Check credibility of all URLs in parallel (cap at 10)
    async def _check_one(url: str) -> tuple[str, dict]:
        try:
            raw = await _check(url)
            return url, json.loads(raw)
        except Exception:
            return url, {"credibility_score": 0.5, "tier": "unknown"}

    pairs = await asyncio.gather(*[_check_one(u) for u in urls[:10]])
    credibility_results: dict[str, dict] = dict(pairs)

    # Build credibility context for the LLM
    cred_summary = ""
    if credibility_results:
        lines = []
        for url, info in credibility_results.items():
            score = info.get("credibility_score", info.get("score", "?"))
            tier = info.get("tier", "?")
            lines.append(f"  - {url}: score={score}, tier={tier}")
        cred_summary = "Source credibility check:\n" + "\n".join(lines)

    prompt_parts = [
        f"You are a research synthesis expert. Your job is to produce a final, "
        f"coherent answer to the research question using the provided findings.",
        f"\nResearch question: {query}",
    ]

    if web_findings:
        prompt_parts.append(f"\nWeb research findings:\n{web_findings}")
    if rag_findings:
        prompt_parts.append(f"\nDocument corpus findings:\n{rag_findings}")
    if cred_summary:
        prompt_parts.append(f"\n{cred_summary}")

    prompt_parts.append(
        "\nWrite a final answer that:\n"
        "1. Directly addresses the research question\n"
        "2. Integrates findings from both sources where available\n"
        "3. Prioritises high-credibility sources\n"
        "4. Includes inline citations for key claims\n"
        "5. Ends with a 'References' section listing the sources used\n"
        "\nFinal answer:"
    )

    prompt = "\n".join(prompt_parts)

    client = _get_client()
    response = await client.chat.completions.create(
        model=os.environ.get("SUMMARISER_LLM", "gpt-5.4-mini"),
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content or ""
