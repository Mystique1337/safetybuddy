"""Durable storage for SafetyBuddy runtime state: usage events, PPE violation
alerts, and answer feedback.

Previously these lived in a process-local dict that vanished on restart. They now
persist to the self-hosted Supabase schema over its REST API (see src/db.py and
supabase/schema.sql). When the Supabase REST credentials are unset the module
falls back to an in-memory store with the same shapes, so the app still runs for
local UI work without a database.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from src.config import settings
from src.db import count_rows, insert, select

# In-memory fallback (used only when no database is configured).
_mem = {"events": [], "alerts": [], "feedback": [], "subscribers": []}
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
        insert("events", {
            "kind": kind, "mode": mode, "query": query,
            "tokens": tokens, "metadata": meta,
        })
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
        insert("alerts", {
            "source": source, "severity": severity, "summary": summary,
            "time_label": time_label, "metadata": meta,
        })
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
        insert("feedback", {
            "message_id": message_id, "rating": rating,
            "comment": comment, "query": query, "answer": answer,
        })
    except Exception as e:
        print(f"Warning: log_feedback failed ({e}).")


def subscribe(email: str, wants_updates: bool = True, source: str | None = None) -> bool:
    """Store an opt-in email for product updates. Idempotent on email."""
    email = (email or "").strip().lower()
    if not email:
        return False
    if not settings.db_enabled:
        row = {"id": _next_id(), "email": email, "wants_updates": wants_updates,
               "source": source, "created_at": _now_iso()}
        with _mem_lock:
            if not any(s["email"] == email for s in _mem["subscribers"]):
                _mem["subscribers"].append(row)
        return True
    try:
        insert(
            "subscribers",
            {"email": email, "wants_updates": wants_updates, "source": source},
            on_conflict="email",
            prefer="resolution=merge-duplicates,return=minimal",
        )
        return True
    except Exception as e:
        print(f"Warning: subscribe failed ({e}).")
        return False


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def recent_alerts(limit: int = 50) -> list:
    """Most-recent alerts, newest first, in dashboard shape."""
    if not settings.db_enabled:
        with _mem_lock:
            return list(reversed(_mem["alerts"][-limit:]))
    try:
        rows = select(
            "alerts", "id,source,severity,summary,time_label,created_at",
            order="created_at.desc", limit=limit,
        ).json()
        return [{
            "id": r["id"], "source": r["source"], "severity": r["severity"],
            "summary": r["summary"], "time": r["time_label"],
            "timestamp": r["created_at"],
        } for r in rows]
    except Exception as e:
        print(f"Warning: recent_alerts failed ({e}).")
        return []


def dashboard() -> dict:
    """Aggregate counters + recent alerts + recent chat messages."""
    if not settings.db_enabled:
        with _mem_lock:
            events = _mem["events"]
            today = _now_iso()[:10]
            stats = {
                "violations_today": sum(1 for a in _mem["alerts"] if (a.get("created_at") or "")[:10] == today),
                "violations": len(_mem["alerts"]),
                "inspections": sum(1 for e in events if e["kind"] in ("image", "video")),
                "questions": sum(1 for e in events if e["kind"] == "chat"),
            }
            recent_messages = [{
                "id": e["id"], "timestamp": e["created_at"],
                "query": (e.get("query") or "")[:100], "mode": e.get("mode"),
            } for e in reversed(events) if e["kind"] == "chat"][:20]
        return {"stats": stats, "alerts": recent_alerts(50), "recent_messages": recent_messages}
    try:
        day_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
        stats = {
            "violations_today": count_rows("alerts", created_at=f"gte.{day_start}"),
            "violations": count_rows("alerts"),
            "inspections": count_rows("events", kind="in.(image,video)"),
            "questions": count_rows("events", kind="eq.chat"),
        }
        rows = select(
            "events", "id,created_at,query,mode",
            kind="eq.chat", order="created_at.desc", limit=20,
        ).json()
        recent_messages = [{
            "id": r["id"], "timestamp": r["created_at"],
            "query": (r["query"] or "")[:100], "mode": r["mode"],
        } for r in rows]
        return {"stats": stats, "alerts": recent_alerts(50), "recent_messages": recent_messages}
    except Exception as e:
        print(f"Warning: dashboard read failed ({e}).")
        return {"stats": {"queries": 0, "images_analyzed": 0, "video_frames": 0, "violations": 0},
                "alerts": [], "recent_messages": []}
