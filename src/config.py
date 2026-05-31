"""Central configuration for SafetyBuddy, read from environment variables.

Values are read at import time. In Modal they arrive via an attached Secret; in
local dev they come from a .env loaded by the Flask entrypoint
(`src/ui/flask_app.py`). Every variable is documented in `.env.example`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _b(name: str, default: bool) -> bool:
    return os.environ.get(name, str(int(default))).strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # --- Gemma 4 model serving (vLLM on Modal, OpenAI-compatible) ---
    model_repo: str = os.environ.get("MODEL_REPO", "google/gemma-4-E4B-it")
    llm_gpu: str = os.environ.get("LLM_GPU", "L4")            # L4 (24GB) fits E4B and is cheapest
    llm_scaledown_window: int = _i("LLM_SCALEDOWN_WINDOW", 120)
    max_model_len: int = _i("MAX_MODEL_LEN", 8192)

    # Where the app sends chat/vision requests (the Gemma OpenAI-compatible /v1
    # endpoint). Empty -> the OpenAI SDK default base URL (point at a local vLLM
    # in dev). `llm_api_key` is the bearer token vLLM enforces with --api-key.
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "")
    llm_api_key: str = os.environ.get("LLM_API_KEY", "")
    vision_model: str = os.environ.get("VISION_MODEL", "google/gemma-4-E4B-it")
    chat_model: str = os.environ.get("CHAT_MODEL", "google/gemma-4-E4B-it")
    # Gemma vision image token budget: 70 / 140 / 280 / 560 / 1120 (detail vs speed).
    vision_image_tokens: int = _i("VISION_IMAGE_TOKENS", 560)

    # --- Embeddings (nomic-embed-text-v1.5, runs on CPU) ---
    embed_model: str = os.environ.get("EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5")
    embed_dim: int = _i("EMBED_DIM", 768)

    # --- Self-hosted Supabase (pgvector vector store + analytics) ---
    # Direct Postgres URL; all SafetyBuddy tables live in their own schema.
    supabase_db_url: str = os.environ.get("SUPABASE_DB_URL", "")
    supabase_db_schema: str = os.environ.get("SUPABASE_DB_SCHEMA", "safety_buddy")
    supabase_url: str = os.environ.get("SUPABASE_URL", "")
    supabase_service_role_key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    # --- RAG tuning ---
    top_k: int = _i("RAG_TOP_K", 20)            # candidates pulled from the store
    final_k: int = _i("RAG_FINAL_K", 5)         # passages kept for the answer
    chunk_chars: int = _i("RAG_CHUNK_CHARS", 1200)
    chunk_overlap: int = _i("RAG_CHUNK_OVERLAP", 200)

    # --- Generation defaults ---
    temperature: float = _f("LLM_TEMPERATURE", 0.2)
    max_tokens: int = _i("LLM_MAX_TOKENS", 1500)

    # --- Flask ---
    secret_key: str = os.environ.get("SECRET_KEY", "safetybuddy-dev-key-change-in-prod")
    port: int = _i("PORT", 6768)

    @property
    def db_enabled(self) -> bool:
        """True when a Supabase/Postgres URL is configured (else the app runs
        with in-memory state and an empty knowledge base)."""
        return bool(self.supabase_db_url)


settings = Settings()

APP_NAME = "safetybuddy"
