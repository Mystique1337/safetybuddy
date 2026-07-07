"""PostgREST client for SafetyBuddy's self-hosted Supabase.

The self-hosted Supabase instance exposes only its REST API (PostgREST behind
Kong at ``SUPABASE_URL``), not a raw Postgres port, so every read and write goes
over HTTPS. Requests are scoped to the SafetyBuddy schema (``SUPABASE_DB_SCHEMA``)
with the Accept-Profile / Content-Profile headers and authenticated with the
service-role key (server-side only, never shipped to a browser).

Vector search runs through the SQL functions in supabase/schema.sql, invoked as
PostgREST RPCs (``/rest/v1/rpc/<fn>``). pgvector arguments are sent in their text
form ``"[0.1,0.2,...]"`` (see ``vector_literal``), which Postgres parses into
``vector``.

Both the vector store (src/rag/vectorstore.py) and the analytics/alerts storage
(src/storage/db.py) share the single client returned by ``get_client``. When the
REST credentials are unset the app degrades gracefully to in-memory state, so it
still boots for local UI work without a database.
"""
from __future__ import annotations

from src.config import settings

_client = None


def get_client():
    """Lazily build the shared httpx client scoped to the SafetyBuddy schema."""
    global _client
    if _client is None:
        import httpx

        key = settings.supabase_service_role_key
        schema = settings.supabase_db_schema
        _client = httpx.Client(
            base_url=settings.supabase_url.rstrip("/") + "/rest/v1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                # Scope every request to the app's own schema, not public.
                "Accept-Profile": schema,
                "Content-Profile": schema,
                "Content-Type": "application/json",
            },
            timeout=settings.http_timeout,
        )
    return _client


def vector_literal(vec) -> str:
    """pgvector text form ``"[v1,v2,...]"`` — PostgREST casts it to ``vector``."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


# --------------------------------------------------------------------------- #
# Thin PostgREST verbs. `filters` are raw PostgREST query params, e.g.
# ``kind="eq.chat"`` or ``created_at="gte.2026-01-01"``.
# --------------------------------------------------------------------------- #
def select(table, columns="*", *, order=None, limit=None, count=None, **filters):
    """GET rows from `table`; returns the httpx Response (use .json())."""
    params = {"select": columns, **filters}
    if order:
        params["order"] = order
    if limit is not None:
        params["limit"] = limit
    headers = {"Prefer": f"count={count}"} if count else None
    r = get_client().get(f"/{table}", params=params, headers=headers)
    r.raise_for_status()
    return r


def insert(table, rows, *, on_conflict=None, prefer="return=minimal"):
    """POST one row (dict) or many (list). `on_conflict` turns it into an upsert."""
    params = {"on_conflict": on_conflict} if on_conflict else None
    r = get_client().post(f"/{table}", params=params, json=rows,
                          headers={"Prefer": prefer})
    r.raise_for_status()
    return r


def update(table, values, *, prefer="return=minimal", **filters):
    """PATCH rows matching `filters`."""
    r = get_client().patch(f"/{table}", params=filters, json=values,
                           headers={"Prefer": prefer})
    r.raise_for_status()
    return r


def delete(table, **filters):
    """DELETE rows matching `filters`."""
    r = get_client().request("DELETE", f"/{table}", params=filters)
    r.raise_for_status()
    return r


def rpc(fn, payload=None):
    """Call a Postgres function exposed by PostgREST; returns parsed JSON."""
    r = get_client().post(f"/rpc/{fn}", json=payload or {})
    r.raise_for_status()
    return r.json()


def count_rows(table, **filters) -> int:
    """Exact row count for `table` via the Content-Range header."""
    r = select(table, columns="id", limit=1, count="exact", **filters)
    total = r.headers.get("content-range", "").split("/")[-1]
    try:
        return int(total)
    except (TypeError, ValueError):
        return 0
