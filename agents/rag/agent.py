"""RAG agent using LlamaIndex + vector_db and file_reader MCP tools."""
import json
import os
from typing import Callable, Awaitable

from llama_index.core import Settings
from llama_index.core.llms import LLM
from llama_index.llms.openai import OpenAI

from agents.rag.mcp_client import search_documents, read_file


def _get_llm() -> LLM:
    return OpenAI(
        model=os.environ.get("RAG_LLM", "gpt-4o-mini"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )


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
        hits = json.loads(raw_results)
    except json.JSONDecodeError:
        hits = [{"content": raw_results, "source": "unknown"}]

    if not hits:
        return "No relevant documents found in the corpus for this query."

    # 3. Build a context string from the retrieved passages
    context_parts = []
    sources = []
    for hit in hits:
        content = hit.get("content", hit.get("text", ""))
        source = hit.get("source", hit.get("id", "unknown"))
        if content:
            context_parts.append(f"[Source: {source}]\n{content}")
            sources.append(source)

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

    # Append source list
    if sources:
        answer_text += f"\n\nSources consulted: {', '.join(set(sources))}"

    return answer_text
