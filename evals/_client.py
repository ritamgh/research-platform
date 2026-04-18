"""HTTP client for calling the research orchestrator endpoint."""
import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 120.0


def call_research_endpoint(
    query: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Call POST /research and return the response dict.

    On timeout or connection error, returns an error-shaped dict rather than
    raising so a single slow query doesn't abort the entire eval run.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base_url}/research", json={"query": query})
        if resp.status_code == 200:
            return resp.json()
        return {
            "answer": "",
            "sources": [],
            "route": "error",
            "retrieved_context": [],
            "error": f"http_{resp.status_code}",
        }
    except (httpx.ReadTimeout, httpx.ConnectError, httpx.TimeoutException) as exc:
        return {
            "answer": "",
            "sources": [],
            "route": "error",
            "retrieved_context": [],
            "error": str(exc),
        }
