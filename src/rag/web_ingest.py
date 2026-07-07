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
from src.db import delete, insert, select, update
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
    rows = select("kb_sources", "content_hash,fetched_at",
                  url=f"eq.{url}", limit=1).json()
    row = rows[0] if rows else None
    if row and row.get("fetched_at"):
        # Parse the ISO timestamp so the TTL check can compare datetimes.
        row["fetched_at"] = datetime.fromisoformat(row["fetched_at"])
    return row


def _upsert_source(url, content_hash, title, doc_type, tier) -> None:
    insert(
        "kb_sources",
        {"url": url, "content_hash": content_hash, "title": title,
         "doc_type": doc_type, "tier": tier,
         "fetched_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="url",
        prefer="resolution=merge-duplicates,return=minimal",
    )


def _touch_source(url: str) -> None:
    update("kb_sources", {"fetched_at": datetime.now(timezone.utc).isoformat()},
           url=f"eq.{url}")


def _delete_chunks_for_url(url: str) -> None:
    delete("kb_chunks", source_url=f"eq.{url}")


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
