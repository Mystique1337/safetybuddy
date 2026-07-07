"""Vector store backed by self-hosted Supabase (Postgres + pgvector).

All SafetyBuddy tables live in their own schema (``SUPABASE_DB_SCHEMA``, default
``safety_buddy``) so they never collide with other apps on the same instance.
Retrieval uses hybrid search (dense pgvector cosine + Postgres full-text, fused
with Reciprocal Rank Fusion) defined in supabase/schema.sql.

Access is over Supabase's REST API (PostgREST): chunks are upserted into the
``kb_chunks`` table, and retrieval/stats call the ``hybrid_search`` and
``kb_stats`` SQL functions as RPCs. Embeddings travel as pgvector text literals
(see ``src.db.vector_literal``). If the Supabase REST credentials are unset the
store degrades gracefully: ``retrieve`` returns nothing and ``ingest_chunks`` is
a no-op, so the app still boots for local UI work.
"""
from __future__ import annotations

from src.config import settings
from src.db import insert, rpc, vector_literal
from src.rag.embeddings import embed_query, embed_texts

# Rows per PostgREST insert request (embeddings are large; keep bodies sane).
_INGEST_BATCH = 100


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
def ingest_chunks(chunks: list) -> None:
    """Embed and upsert chunks. Idempotent on the chunker's chunk id.

    chunks: list of {"id": str, "content": str, "metadata": dict}
    """
    if not chunks:
        return
    if not settings.db_enabled:
        print("Supabase REST credentials not set — skipping ingestion. Fill in .env and re-run.")
        return

    contents = [c["content"] for c in chunks]
    print(f"Embedding {len(contents)} chunks with {settings.embed_model} (CPU)...")
    embeddings = embed_texts(contents, mode="document")

    rows = []
    for c, emb in zip(chunks, embeddings):
        md = c.get("metadata", {}) or {}
        page = md.get("page")
        rows.append({
            "chunk_uid": c["id"],
            "content": c["content"],
            "embedding": vector_literal(emb),
            "filename": md.get("filename"),
            "doc_type": md.get("doc_type"),
            "page": int(page) if isinstance(page, (int, float)) else None,
            "source_url": md.get("source_url"),
            "metadata": md,
        })

    # Upsert; ON CONFLICT (chunk_uid) DO NOTHING == ignore-duplicates.
    for i in range(0, len(rows), _INGEST_BATCH):
        insert(
            "kb_chunks", rows[i:i + _INGEST_BATCH],
            on_conflict="chunk_uid",
            prefer="resolution=ignore-duplicates,return=minimal",
        )
    print(f"Ingested {len(rows)} chunks into Supabase schema '{settings.supabase_db_schema}'.")


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
def retrieve(query: str, n_results: int = 5, doc_type: str | None = None) -> list:
    """Hybrid-retrieve relevant chunks for a query.

    Returns a list of {"content", "metadata", "score"} matching the shape the
    RAG chains expect. Returns [] (with a warning) if the store is unavailable.
    """
    if not settings.db_enabled:
        return []
    try:
        emb = embed_query(query)
        # Over-fetch when filtering by doc_type, then filter in Python.
        fetch = n_results * 4 if doc_type else n_results

        rows = rpc("hybrid_search", {
            "query_text": query,
            "query_embedding": vector_literal(emb),
            "match_count": fetch,
        })
    except Exception as e:  # missing schema, network, etc. — degrade gracefully
        print(f"Warning: vector retrieval failed ({e}). Returning no context.")
        return []

    results = []
    for r in rows:
        md = r.get("metadata") or {}
        if doc_type and md.get("doc_type") != doc_type:
            continue
        score = r.get("score")
        if score is None:
            score = r.get("similarity") or 0.0
        results.append({
            "content": r["content"], "metadata": md,
            "score": float(score),
            "similarity": float(r.get("similarity") or 0.0),
        })
        if len(results) >= n_results:
            break
    return results


def kb_stats() -> dict:
    """Lightweight knowledge-base counts for health/status endpoints."""
    if not settings.db_enabled:
        return {"chunks": 0, "doc_types": 0, "last_ingest": None}
    try:
        rows = rpc("kb_stats", {})
        return rows[0] if rows else {"chunks": 0, "doc_types": 0, "last_ingest": None}
    except Exception:
        return {"chunks": 0, "doc_types": 0, "last_ingest": None}
