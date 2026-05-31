"""Shared OpenAI-compatible client for SafetyBuddy.

Both the vision analyzer and the RAG chat talk to the self-hosted Gemma 4 model
(served by vLLM on Modal) through this single client. Because vLLM exposes an
OpenAI-compatible API, the rest of the app keeps using the familiar
`client.chat.completions.create(...)` calls — only the base URL and model name
change relative to the old GPT-4o setup.
"""
from openai import OpenAI

from src.config import settings

_client: OpenAI | None = None


def get_llm_client() -> OpenAI:
    """Lazily build the OpenAI client pointed at the Gemma endpoint.

    `LLM_BASE_URL` selects the server (e.g. the Modal Gemma URL ending in `/v1`,
    or a local vLLM in dev); empty falls back to the SDK default. `LLM_API_KEY`
    is the bearer token vLLM enforces with `--api-key`.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=(settings.llm_base_url or None),
            api_key=(settings.llm_api_key or "not-needed"),
            timeout=120.0,
            max_retries=2,
        )
    return _client
