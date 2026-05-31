"""Durable storage for SafetyBuddy runtime state: usage events, PPE violation
alerts, and answer feedback.

Previously these lived in a process-local dict that vanished on restart. They now
persist to the self-hosted Supabase schema (see supabase/schema.sql). When
``SUPABASE_DB_URL`` is unset the module falls back to an in-memory store with the
same shapes, so the app still runs for local UI work without a database.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from src.config import settings
from src.db import get_pool

# In-memory fallback (used only when no database is configured).
_mem = {"events": [], "alerts": [], "feedback": []}
_mem_seq = {"n": 0}
_mem_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_id() -> int:
    with _mem_lock:
        _mem_seq["n"] += 1
        return _mem_seq["n"]


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def log_event(kind: str, mode: str | None = None, query: str | None = None,
              tokens: int | None = None, meta: dict | None = None) -> None:
    """Record a usage event (kind: chat / image / video / live_frame)."""
    meta = meta or {}
    if not settings.db_enabled:
        row = {
            "id": _next_id(), "kind": kind, "mode": mode, "query": query,
            "tokens": tokens, "metadata": meta, "created_at": _now_iso(),
        }
        with _mem_lock:
            _mem["events"].append(row)
        return
    try:
        from psycopg.types.json import Json

        pool = get_pool()
        with pool.connection() as conn:
            conn.execute(
                "INSERT INTO events (kind, mode, query, tokens, metadata) "
                "VALUES (%s, %s, %s, %s, %s)",
                (kind, mode, query, tokens, Json(meta)),
            )
    except Exception as e:
        print(f"Warning: log_event failed ({e}).")


def log_alert(source: str, severity: str, summary: str,
              time_label: str, meta: dict | None = None) -> dict:
    """Record a PPE violation alert and return it in dashboard shape."""
    meta = meta or {}
    alert = {
        "source": source, "severity": severity, "summary": summary,
        "time": time_label, "timestamp": _now_iso(),
    }
    if not settings.db_enabled:
        row = {"id": _next_id(), **alert}
        with _mem_lock:
            _mem["alerts"].append(row)
        return alert
    try:
        from psycopg.types.json import Json

        pool = get_pool()
        with pool.connection() as conn:
            conn.execute(
                "INSERT INTO alerts (source, severity, summary, time_label, metadata) "
                "VALUES (%s, %s, %s, %s, %s)",
                (source, severity, summary, time_label, Json(meta)),
            )
    except Exception as e:
        print(f"Warning: log_alert failed ({e}).")
    return alert


def log_feedback(message_id: str | None, rating: int, comment: str | None = None,
                 query: str | None = None, answer: str | None = None) -> None:
    """Store a thumbs-up/down (rating +1/-1) on an answer."""
    if not settings.db_enabled:
        row = {
            "id": _next_id(), "message_id": message_id, "rating": rating,
            "comment": comment, "query": query, "answer": answer,
            "created_at": _now_iso(),
        }
        with _mem_lock:
            _mem["feedback"].append(row)
        return
    try:
        pool = get_pool()
        with pool.connection() as conn:
            conn.execute(
                "INSERT INTO feedback (message_id, rating, comment, query, answer) "
                "VALUES (%s, %s, %s, %s, %s)",
                (message_id, rating, comment, query, answer),
            )
    except Exception as e:
        print(f"Warning: log_feedback failed ({e}).")


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def recent_alerts(limit: int = 50) -> list:
    """Most-recent alerts, newest first, in dashboard shape."""
    if not settings.db_enabled:
        with _mem_lock:
            return list(reversed(_mem["alerts"][-limit:]))
    try:
        from psycopg.rows import dict_row

        pool = get_pool()
        with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, source, severity, summary, time_label, created_at "
                "FROM alerts ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [{
                "id": r["id"], "source": r["source"], "severity": r["severity"],
                "summary": r["summary"], "time": r["time_label"],
                "timestamp": r["created_at"].isoformat(),
            } for r in cur.fetchall()]
    except Exception as e:
        print(f"Warning: recent_alerts failed ({e}).")
        return []


def dashboard() -> dict:
    """Aggregate counters + recent alerts + recent chat messages."""
    if not settings.db_enabled:
        with _mem_lock:
            events = _mem["events"]
            stats = {
                "queries": sum(1 for e in events if e["kind"] == "chat"),
                "images_analyzed": sum(1 for e in events if e["kind"] == "image"),
                "video_frames": sum(int((e.get("metadata") or {}).get("frames", 0))
                                    for e in events if e["kind"] == "video"),
                "violations": len(_mem["alerts"]),
            }
            recent_messages = [{
                "id": e["id"], "timestamp": e["created_at"],
                "query": (e.get("query") or "")[:100], "mode": e.get("mode"),
            } for e in reversed(events) if e["kind"] == "chat"][:20]
        return {"stats": stats, "alerts": recent_alerts(50), "recent_messages": recent_messages}
    try:
        from psycopg.rows import dict_row

        pool = get_pool()
        with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT
                     (SELECT count(*) FROM events WHERE kind='chat')   AS queries,
                     (SELECT count(*) FROM events WHERE kind='image')  AS images_analyzed,
                     (SELECT COALESCE(SUM((metadata->>'frames')::int),0)
                        FROM events WHERE kind='video')                AS video_frames,
                     (SELECT count(*) FROM alerts)                     AS violations"""
            )
            stats = dict(cur.fetchone())
            cur.execute(
                "SELECT id, created_at, query, mode FROM events "
                "WHERE kind='chat' ORDER BY created_at DESC LIMIT 20"
            )
            recent_messages = [{
                "id": r["id"], "timestamp": r["created_at"].isoformat(),
                "query": (r["query"] or "")[:100], "mode": r["mode"],
            } for r in cur.fetchall()]
        return {"stats": stats, "alerts": recent_alerts(50), "recent_messages": recent_messages}
    except Exception as e:
        print(f"Warning: dashboard read failed ({e}).")
        return {"stats": {"queries": 0, "images_analyzed": 0, "video_frames": 0, "violations": 0},
                "alerts": [], "recent_messages": []}
