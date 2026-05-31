"""Vector store backed by self-hosted Supabase (Postgres + pgvector).

All SafetyBuddy tables live in their own schema (``SUPABASE_DB_SCHEMA``, default
``safety_buddy``) so they never collide with other apps on the same instance.
Retrieval uses hybrid search (dense pgvector cosine + Postgres full-text, fused
with Reciprocal Rank Fusion) defined in supabase/schema.sql.

Sync access via psycopg3 with a small connection pool, which fits the Flask
request model. If ``SUPABASE_DB_URL`` is unset the store degrades gracefully:
``retrieve`` returns nothing and ``ingest_chunks`` is a no-op, so the app still
boots for local UI work.
"""
from __future__ import annotations

from src.config import settings
from src.rag.embeddings import embed_query, embed_texts

_pool = None


def _get_pool():
    """Lazily build a pgvector-aware connection pool (search_path = schema)."""
    global _pool
    if _pool is None:
        from pgvector.psycopg import register_vector
        from psycopg_pool import ConnectionPool

        def _configure(conn):
            register_vector(conn)

        _pool = ConnectionPool(
            conninfo=settings.supabase_db_url,
            min_size=1,
            max_size=8,
            kwargs={
                "autocommit": True,
                "options": f"-c search_path={settings.supabase_db_schema},public",
            },
            configure=_configure,
            open=True,
        )
    return _pool


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
        print("SUPABASE_DB_URL not set — skipping ingestion. Fill in .env and re-run.")
        return

    from psycopg.types.json import Json

    contents = [c["content"] for c in chunks]
    print(f"Embedding {len(contents)} chunks with {settings.embed_model} (CPU)...")
    embeddings = embed_texts(contents, mode="document")

    rows = []
    for c, emb in zip(chunks, embeddings):
        md = c.get("metadata", {}) or {}
        page = md.get("page")
        rows.append((
            c["id"], c["content"], emb,
            md.get("filename"), md.get("doc_type"),
            int(page) if isinstance(page, (int, float)) else None,
            Json(md),
        ))

    pool = _get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO kb_chunks
                (chunk_uid, content, embedding, filename, doc_type, page, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_uid) DO NOTHING
            """,
            rows,
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
        from psycopg.rows import dict_row

        emb = embed_query(query)
        # Over-fetch when filtering by doc_type, then filter in Python.
        fetch = n_results * 4 if doc_type else n_results

        pool = _get_pool()
        with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT content, metadata, score, similarity "
                "FROM hybrid_search(%s, %s, %s)",
                (query, emb, fetch),
            )
            rows = cur.fetchall()
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
        results.append({"content": r["content"], "metadata": md, "score": float(score)})
        if len(results) >= n_results:
            break
    return results


def kb_stats() -> dict:
    """Lightweight knowledge-base counts for health/status endpoints."""
    if not settings.db_enabled:
        return {"chunks": 0, "doc_types": 0, "last_ingest": None}
    try:
        from psycopg.rows import dict_row

        pool = _get_pool()
        with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM kb_stats()")
            row = cur.fetchone()
        return dict(row) if row else {"chunks": 0, "doc_types": 0, "last_ingest": None}
    except Exception:
        return {"chunks": 0, "doc_types": 0, "last_ingest": None}
