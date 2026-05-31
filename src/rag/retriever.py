"""Self-improving retrieval.

Retrieve from the local Supabase store; if coverage is weak (top cosine
similarity below RAG_COVERAGE_THRESHOLD, or too few chunks), pull authoritative
sources in live, ingest them, and re-retrieve so the answer uses fresh context.
A best-effort background thread also tops the knowledge base up after queries,
so it grows the more the app is used.
"""
from __future__ import annotations

import threading

from src.config import settings
from src.rag.vectorstore import retrieve

# At most one background enrichment in flight at a time (avoid thread pile-up).
_bg_busy = threading.Event()


def _coverage(hits: list) -> float:
    if not hits:
        return 0.0
    return max(h.get("similarity", 0.0) for h in hits)


def _enrich(query: str, max_urls: int) -> int:
    """Fetch + ingest candidate sources for the query. Returns sources added."""
    from src.rag.sources import search_urls
    from src.rag.web_ingest import ingest_url

    added = 0
    for url in search_urls(query, max_urls):
        try:
            if ingest_url(url).get("added"):
                added += 1
        except Exception as e:
            print(f"Warning: enrichment of {url} failed ({e}).")
    return added


def _spawn_bg_enrich(query: str) -> None:
    if _bg_busy.is_set():
        return
    _bg_busy.set()

    def _run():
        try:
            _enrich(query, 1)
        finally:
            _bg_busy.clear()

    threading.Thread(target=_run, daemon=True).start()


def retrieve_with_coverage(query: str, n_results: int = 5, doc_type: str | None = None):
    """Return (hits, meta). meta = {coverage, enriched, kb_added}."""
    hits = retrieve(query, n_results=n_results, doc_type=doc_type)
    coverage = _coverage(hits)
    enriched = False
    kb_added = 0

    weak = coverage < settings.coverage_threshold or len(hits) < settings.min_chunks
    if weak and settings.enable_web_enrich and settings.db_enabled:
        kb_added = _enrich(query, settings.enrich_max_urls)
        if kb_added:
            hits = retrieve(query, n_results=n_results, doc_type=doc_type)
            coverage = _coverage(hits)
            enriched = True

    # Keep growing the KB in the background after the answer is served.
    if settings.always_enrich and settings.enable_web_enrich and settings.db_enabled:
        _spawn_bg_enrich(query)

    return hits, {"coverage": round(coverage, 3), "enriched": enriched, "kb_added": kb_added}
