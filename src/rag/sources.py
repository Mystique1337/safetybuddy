"""Authoritative source catalog + web-search bias for SafetyBuddy's RAG.

These are the seed documents the knowledge base grows from, and the domains we
bias live web search toward when local coverage is weak. Tiers: 1 = official /
regulatory, 2 = standards / reference, 3 = other.
"""
from __future__ import annotations

import hashlib

# Domains we trust for PPE / occupational-safety content (web-search bias).
AUTHORITATIVE_DOMAINS = [
    "osha.gov", "cdc.gov", "hse.gov.uk", "osha.europa.eu", "europa.eu",
    "ansi.org", "nfpa.org", "en.wikipedia.org",
]
# Subset treated as tier-1 official/regulatory.
OFFICIAL_DOMAINS = ["osha.gov", "cdc.gov", "hse.gov.uk", "europa.eu"]

# Curated seed sources. The knowledge base is seeded from these (scripts/seed_kb.py)
# and the self-improving retriever falls back to them when no web-search key is set.
SEED_SOURCES = [
    {"url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.132",
     "title": "OSHA 1910.132 - PPE general requirements", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.133",
     "title": "OSHA 1910.133 - Eye and face protection", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.135",
     "title": "OSHA 1910.135 - Head protection", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.136",
     "title": "OSHA 1910.136 - Foot protection", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.137",
     "title": "OSHA 1910.137 - Electrical protective equipment", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.138",
     "title": "OSHA 1910.138 - Hand protection", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/personal-protective-equipment",
     "title": "OSHA - Personal Protective Equipment overview", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/respiratory-protection",
     "title": "OSHA - Respiratory protection", "doc_type": "regulation"},
    {"url": "https://www.osha.gov/sites/default/files/publications/osha3151.pdf",
     "title": "OSHA 3151 - Personal Protective Equipment (booklet)", "doc_type": "safety_manual"},
    {"url": "https://www.cdc.gov/niosh/ppe/about/index.html",
     "title": "NIOSH - Personal protective equipment", "doc_type": "safety_manual"},
    {"url": "https://www.hse.gov.uk/ppe/index.htm",
     "title": "HSE (UK) - Personal protective equipment", "doc_type": "safety_manual"},
    {"url": "https://en.wikipedia.org/wiki/Personal_protective_equipment",
     "title": "Personal protective equipment (overview)", "doc_type": "reference"},
]


def domain_tier(url: str) -> int:
    u = url.lower()
    if any(d in u for d in OFFICIAL_DOMAINS):
        return 1
    if any(d in u for d in ("ansi.org", "nfpa.org", "wikipedia.org")):
        return 2
    return 3


def guess_doc_type(url: str) -> str:
    u = url.lower()
    if "wikipedia.org" in u:
        return "reference"
    if any(d in u for d in ("hse.gov.uk", "europa.eu", "cdc.gov")):
        return "safety_manual"
    if "osha.gov" in u:
        return "regulation"
    return "general"


def source_uid(url: str) -> str:
    """Stable id prefix for a URL's chunks (used as chunk_uid base)."""
    return "src_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def search_urls(query: str, max_results: int = 5) -> list:
    """Return candidate URLs for enrichment: live web search biased to
    authoritative domains when TAVILY_API_KEY is set, else the curated seeds."""
    from src.config import settings

    urls: list = []
    if settings.tavily_api_key:
        try:
            urls = _tavily_search(query, max_results)
        except Exception as e:
            print(f"Warning: Tavily search failed ({e}); using seed sources.")
    if not urls:
        urls = [s["url"] for s in SEED_SOURCES]

    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:max_results]


def _tavily_search(query: str, max_results: int) -> list:
    import httpx

    from src.config import settings

    resp = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": settings.tavily_api_key,
            "query": f"{query} personal protective equipment OSHA safety",
            "max_results": max_results,
            "search_depth": "basic",
            "include_domains": AUTHORITATIVE_DOMAINS,
        },
        timeout=settings.http_timeout,
    )
    resp.raise_for_status()
    return [r["url"] for r in resp.json().get("results", []) if r.get("url")]
