"""Live ingestion of web/PDF sources into the Supabase pgvector store.

Fetch a URL, clean it to text (trafilatura for HTML, PyMuPDF for PDF), chunk,
embed, and upsert. A small kb_sources table tracks what has been ingested, its
content hash, and when, so we skip sources that are still fresh
(RAG_DOC_TTL_DAYS) and re-ingest only when content actually changed. This is the
mechanism behind the self-improving RAG: weak queries pull authoritative sources
in, and the knowledge base keeps growing as the app is used.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from src.config import settings
from src.db import get_pool
from src.ingestion.chunker import chunk_documents
from src.ingestion.document_loader import Document
from src.rag.sources import domain_tier, guess_doc_type, source_uid


# --------------------------------------------------------------------------- #
# Fetch + clean
# --------------------------------------------------------------------------- #
def fetch_text(url: str) -> str:
    """Download a URL and return clean main-body text ('' if nothing useful)."""
    import httpx

    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(follow_redirects=True, timeout=settings.http_timeout, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").lower()
        data = resp.content

    if "pdf" in ctype or url.lower().endswith(".pdf"):
        return _pdf_to_text(data)

    import trafilatura

    html = data.decode("utf-8", errors="replace")
    text = trafilatura.extract(
        html, include_comments=False, include_tables=True, favor_recall=True
    )
    return (text or "").strip()


def _pdf_to_text(data: bytes) -> str:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    parts = [page.get_text("text") for page in doc]
    doc.close()
    return "\n".join(parts).strip()


# --------------------------------------------------------------------------- #
# kb_sources bookkeeping
# --------------------------------------------------------------------------- #
def _get_source(url: str) -> dict | None:
    from psycopg.rows import dict_row

    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT content_hash, fetched_at FROM kb_sources WHERE url = %s", (url,))
        return cur.fetchone()


def _upsert_source(url, content_hash, title, doc_type, tier) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO kb_sources (url, content_hash, title, doc_type, tier, fetched_at)
               VALUES (%s, %s, %s, %s, %s, now())
               ON CONFLICT (url) DO UPDATE SET
                   content_hash = EXCLUDED.content_hash, title = EXCLUDED.title,
                   doc_type = EXCLUDED.doc_type, tier = EXCLUDED.tier, fetched_at = now()""",
            (url, content_hash, title, doc_type, tier),
        )


def _touch_source(url: str) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute("UPDATE kb_sources SET fetched_at = now() WHERE url = %s", (url,))


def _delete_chunks_for_url(url: str) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute("DELETE FROM kb_chunks WHERE source_url = %s", (url,))


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #
def ingest_url(url: str, title: str | None = None, doc_type: str | None = None,
               tier: int | None = None, force: bool = False) -> dict:
    """Fetch, dedup, (re)ingest a single URL. Returns a small status dict."""
    if not settings.db_enabled:
        return {"url": url, "added": False, "reason": "no-db"}

    tier = tier or domain_tier(url)
    doc_type = doc_type or guess_doc_type(url)
    seen = _get_source(url)

    # Skip if still fresh (within the TTL).
    if seen and not force and seen.get("fetched_at"):
        ttl_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.doc_ttl_days)
        if seen["fetched_at"] > ttl_cutoff:
            return {"url": url, "added": False, "reason": "fresh"}

    try:
        text = fetch_text(url)
    except Exception as e:
        return {"url": url, "added": False, "reason": f"fetch-failed: {e}"}
    if not text or len(text) < 200:
        return {"url": url, "added": False, "reason": "empty"}

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if seen and seen.get("content_hash") == content_hash and not force:
        _touch_source(url)
        return {"url": url, "added": False, "reason": "unchanged"}

    title = title or url
    doc = Document(
        content=text,
        metadata={"filename": title, "doc_type": doc_type, "source_url": url, "tier": tier},
        doc_id=source_uid(url),
    )
    chunks = chunk_documents([doc])

    from src.rag.vectorstore import ingest_chunks

    _delete_chunks_for_url(url)   # refresh: drop stale chunks before re-inserting
    ingest_chunks(chunks)
    _upsert_source(url, content_hash, title, doc_type, tier)
    return {"url": url, "added": True, "chunks": len(chunks)}


def ingest_urls(sources: list) -> dict:
    """Ingest a list of seed-source dicts ({url,title,doc_type}) or bare URLs."""
    added, skipped, failed = 0, 0, 0
    for s in sources:
        if isinstance(s, str):
            s = {"url": s}
        r = ingest_url(s["url"], title=s.get("title"), doc_type=s.get("doc_type"))
        if r.get("added"):
            added += 1
            print(f"  + {s['url']} ({r['chunks']} chunks)")
        elif r.get("reason", "").startswith(("fresh", "unchanged")):
            skipped += 1
        else:
            failed += 1
            print(f"  ! {s['url']} -> {r.get('reason')}")
    return {"added": added, "skipped": skipped, "failed": failed}
