"""Shared psycopg3 connection pool for SafetyBuddy (self-hosted Supabase/Postgres).

Both the vector store (src/rag/vectorstore.py) and the analytics/alerts storage
(src/storage/db.py) borrow connections from this single pool. Every connection
is opened with ``search_path`` set to the SafetyBuddy schema (plus public for the
pgvector type), and has the pgvector adapter registered.
"""
from __future__ import annotations

from src.config import settings

_pool = None


def get_pool():
    """Lazily build the pgvector-aware connection pool (search_path = schema)."""
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
