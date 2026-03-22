# mcp_tools/citation_checker/server.py
import json
import time
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP
from mcp.shared.exceptions import McpError, ErrorData
from mcp.types import INVALID_PARAMS

mcp = FastMCP("citation-checker-tool")

# ---------------------------------------------------------------------------
# Domain sets — checked in tier order (first match wins)
# ---------------------------------------------------------------------------

RESEARCH_DOMAINS = {
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "nature.com",
    "science.org", "springer.com", "wiley.com", "cell.com", "nejm.org",
    "thelancet.com", "bmj.com", "plos.org", "jstor.org",
    "semanticscholar.org", "scholar.google.com", "acm.org", "ieee.org",
    "ssrn.com", "researchgate.net", "biorxiv.org", "medrxiv.org",
    "nih.gov", "ncbi.nlm.nih.gov", "sciencedirect.com", "tandfonline.com",
}

CREDIBLE_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "who.int", "cdc.gov",
}

BLOG_HOST_DOMAINS = {
    "wordpress.com", "blogspot.com", "medium.com", "substack.com",
    "tumblr.com", "wix.com", "weebly.com",
}

URL_SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "buff.ly", "short.io",
}

LOW_CREDIBILITY_TLDS = {".click", ".biz", ".info", ".xyz", ".tk", ".ml", ".ga", ".cf"}

TLD_SCORES: dict[str, tuple[float, str, str]] = {
    ".edu": (0.85, "high", "Educational institution domain"),
    ".gov": (0.85, "high", "Government domain"),
    ".org": (0.6, "medium", "Non-profit/organisation domain"),
    ".com": (0.5, "medium", "Commercial domain"),
    ".net": (0.5, "medium", "Commercial domain"),
}
_DEFAULT_TLD_SCORE: tuple[float, str, str] = (0.4, "medium", "Unknown TLD")


def _score_url(url: str) -> tuple[float, str, str]:
    hostname = urlparse(url).hostname or ""
    domain = hostname[4:] if hostname.startswith("www.") else hostname
    tld = ("." + domain.rsplit(".", 1)[-1]) if "." in domain else ""

    if domain in RESEARCH_DOMAINS:
        return (0.9, "high", "Known research publisher")
    if domain in CREDIBLE_NEWS_DOMAINS:
        return (0.9, "high", "Known credible news/health source")
    if domain in BLOG_HOST_DOMAINS:
        return (0.2, "low", "Free blog host")
    if domain in URL_SHORTENER_DOMAINS:
        return (0.2, "low", "URL shortener")
    if tld in LOW_CREDIBILITY_TLDS:
        return (0.1, "low", "Low-credibility TLD")
    return TLD_SCORES.get(tld, _DEFAULT_TLD_SCORE)


@mcp.tool
async def check_credibility(url: str) -> str:
    """Score a URL's credibility using offline domain and TLD heuristics. No HTTP calls."""
    if not url or not url.strip():
        raise McpError(ErrorData(code=INVALID_PARAMS, message="url must not be empty"))
    hostname = urlparse(url).hostname
    if not hostname:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message=f"Could not parse hostname from URL: {url!r}. Ensure a scheme prefix is included (e.g. https://).",
        ))
    score, label, reason = _score_url(url)
    return json.dumps({"url": url, "score": score, "label": label, "reason": reason})
