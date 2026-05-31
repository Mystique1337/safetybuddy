"""nomic-embed-text-v1.5 embeddings (CPU) for the SafetyBuddy vector store.

nomic is a task-prefixed embedding model: stored chunks are embedded with a
``search_document:`` prefix and user queries with ``search_query:``. We add the
right prefix automatically so callers just pass plain text. Output is a 768-dim
L2-normalized vector, matching ``vector(768)`` in supabase/schema.sql.

The model is loaded lazily on first use and cached for the process lifetime, so
the (CPU) load cost is paid once per container.
"""
from __future__ import annotations

from src.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(
            settings.embed_model, trust_remote_code=True, device="cpu"
        )
    return _model


def _prefixed(texts: list[str], mode: str) -> list[str]:
    tag = "search_query" if mode == "query" else "search_document"
    return [f"{tag}: {t}" for t in texts]


def embed_texts(texts: list[str], mode: str = "document") -> list[list[float]]:
    """Embed a list of texts. ``mode`` is 'document' (default) or 'query'."""
    if not texts:
        return []
    model = _get_model()
    vecs = model.encode(
        _prefixed(texts, mode),
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([text], mode="query")[0]
