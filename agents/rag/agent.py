"""RAG agent using LlamaIndex + vector_db and file_reader MCP tools."""
import json
import os
from typing import Callable, Awaitable

from langsmith import traceable, get_current_run_tree
from llama_index.core import Settings
from llama_index.core.llms import LLM
from llama_index.llms.openai import OpenAI

from agents.rag.mcp_client import search_documents


def _get_llm() -> LLM:
    return OpenAI(
        model=os.environ.get("RAG_LLM", "gpt-5.4-mini"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )


@traceable(name="rag_lookup", run_type="chain", tags=["agent"])
async def run_rag_lookup(
    query: str,
    search_fn: Callable[[str, int], Awaitable[str]] | None = None,
) -> str:
    """Run RAG lookup: search the vector DB and synthesise an answer via LlamaIndex.

    ``search_fn`` is injectable for testing.
    """
    _search = search_fn or search_documents

    # 1. Retrieve relevant passages from the vector DB
    raw_results = await _search(query, top_k=5)

    # 2. Parse the results (vector_db returns JSON array of hits)
    try:
        parsed = json.loads(raw_results)
        hits = parsed.get("results", parsed) if isinstance(parsed, dict) else parsed
    except json.JSONDecodeError:
        hits = [{"content": raw_results, "source": "unknown"}]

    if not hits:
        return "[CONFIDENCE: LOW]\nNo relevant documents found in the corpus for this query.\n\n<rag_sources></rag_sources>"

    # 3. Build context and compute confidence from Qdrant similarity scores
    context_parts = []
    sources = []
    scores = []
    for hit in hits:
        content = hit.get("content", hit.get("text", ""))
        title = hit.get("title", "")
        url = hit.get("url", hit.get("source", hit.get("id", "")))
        source = f"{title} ({url})" if title and url else title or url or "unknown"
        score = hit.get("score", 0.0)
        if content:
            context_parts.append(f"[Source: {source}]\n{content}")
            sources.append(source)
            scores.append(score)

    if not context_parts:
        return "[CONFIDENCE: LOW]\nNo relevant content found in the corpus for this query.\n\n<rag_sources></rag_sources>"

    top_score = max(scores)
    avg_score = sum(scores) / len(scores)
    hybrid_score = 0.6 * top_score + 0.4 * avg_score
    if hybrid_score >= 0.65:
        confidence = "HIGH"
    elif hybrid_score >= 0.45:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    rt = get_current_run_tree()
    if rt is not None:
        rt.add_metadata({
            "confidence": confidence,
            "top_score": round(top_score, 4),
            "avg_score": round(avg_score, 4),
            "hybrid_score": round(hybrid_score, 4),
            "num_chunks": len(context_parts),
        })

    context = "\n\n---\n\n".join(context_parts)

    # 4. Use LlamaIndex's OpenAI LLM to synthesise an answer from retrieved context
    llm = _get_llm()
    prompt = (
        f"You are a research assistant. Based ONLY on the following retrieved passages, "
        f"answer the research question. Do not add information not present in the passages.\n\n"
        f"Research question: {query}\n\n"
        f"Retrieved passages:\n{context}\n\n"
        f"Provide a structured answer with:\n"
        f"1. A concise summary (2-3 sentences)\n"
        f"2. Key points from the retrieved documents\n"
        f"3. Source references\n\n"
        f"Answer:"
    )

    response = await llm.acomplete(prompt)
    answer_text = str(response)

    unique_sources = list(dict.fromkeys(sources))
    sources_tag = f'<rag_sources confidence="{confidence}">{" | ".join(unique_sources)}</rag_sources>'

    return f"[CONFIDENCE: {confidence}]\n{answer_text}\n\n{sources_tag}"
