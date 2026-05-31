"""Modal deployment for SafetyBuddy — the single entrypoint that wires everything.

    modal serve  modal_app.py            # local dev (hot-reload, ephemeral URLs)
    modal deploy modal_app.py            # production
    modal run    modal_app.py::seed      # seed the KB with authoritative PPE sources

Components:
  * gemma  — Gemma 4 (E4B) served by vLLM, OpenAI-compatible, on one L4 GPU
             (scale-to-zero, bearer-key protected). Handles both PPE image
             analysis and RAG chat.
  * web    — the existing Flask app served via WSGI. YOLO26 (CPU) and the nomic
             embeddings run in this container; it calls `gemma` over HTTP and
             reads/writes the self-hosted Supabase schema.
  * seed   — one-off knowledge-base seeding from src/rag/sources.py.

Config comes from the Modal secret `safetybuddy-secrets` (created from .env by
scripts/setup_modal_secret.sh). Decorator-time values fall back to the
.env.example defaults so a bare `modal deploy` still does the right thing.
"""
from __future__ import annotations

import os
import subprocess

import modal

APP_NAME = "safetybuddy"
app = modal.App(APP_NAME)

# Read at import time: locally (deploy) for decorator args, and again inside each
# container (where the attached secret has populated the environment).
MODEL_REPO = os.environ.get("MODEL_REPO", "google/gemma-4-E4B-it")
LLM_GPU = os.environ.get("LLM_GPU", "L4")           # L4 (24GB) fits E4B; A100 for 26B-A4B
LLM_SCALEDOWN = int(os.environ.get("LLM_SCALEDOWN_WINDOW", "120"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "8192"))
VLLM_PORT = 8000

HF_CACHE_DIR = "/root/.cache/huggingface"
APP_REMOTE = "/root/safetybuddy"

# Persisted HF cache so Gemma weights + the nomic embedder download once.
hf_cache = modal.Volume.from_name("safetybuddy-hf-cache", create_if_missing=True)
secrets = [modal.Secret.from_name("safetybuddy-secrets")]

# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
# Official vLLM image: it ships the full CUDA toolkit (nvcc) that vLLM's runtime
# kernel JIT needs at startup. A debian_slim + pip install of vLLM lacks nvcc and
# crashes the engine during the profiling run. v0.22.0 already supports gemma-4.
vllm_image = (
    modal.Image.from_registry("vllm/vllm-openai:v0.22.0", add_python="3.12")
    .entrypoint([])  # clear the image's vllm entrypoint so Modal can run the function
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_HOME": HF_CACHE_DIR, "VLLM_USE_V1": "1"})
)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")            # OpenCV runtime libs
    # CPU torch first (saves ~2GB vs the CUDA build; this container has no GPU).
    .pip_install("torch", "torchvision", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install(
        "openai>=1.55.0", "flask>=3.0.0",
        "psycopg[binary,pool]>=3.2.0", "pgvector>=0.3.0",
        "sentence-transformers>=3.0.0", "einops>=0.7.0",
        "ultralytics>=8.4.0", "opencv-python-headless>=4.9.0", "numpy>=1.26.0",
        "pymupdf>=1.24.0", "trafilatura>=1.12.0",
        "python-dotenv>=1.0.0", "Pillow>=10.0.0", "pandas>=2.0.0", "httpx>=0.27.0",
    )
    .env({
        "HF_HOME": HF_CACHE_DIR,
        "SENTENCE_TRANSFORMERS_HOME": HF_CACHE_DIR,
        "PYTHONPATH": APP_REMOTE,
    })
    .workdir(APP_REMOTE)
    .add_local_dir(
        ".", remote_path=APP_REMOTE,
        ignore=[
            "venv", ".venv", ".git", "__pycache__", "*.pyc", "notebooks",
            "data/raw/images", "data/processed", "data/temp_*",
            "Exam Guard*", "exam_guard_app.py", "soro_tts*",
            ".env", "*.log",
        ],
    )
)


# --------------------------------------------------------------------------- #
# Gemma 4 — vLLM OpenAI-compatible server (one L4, scale-to-zero)
# --------------------------------------------------------------------------- #
@app.function(
    image=vllm_image,
    gpu=LLM_GPU,
    volumes={HF_CACHE_DIR: hf_cache},
    secrets=secrets,
    scaledown_window=LLM_SCALEDOWN,
    timeout=24 * 60 * 60,
    max_containers=1,                 # hard cap: never more than one GPU at a time
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=VLLM_PORT, startup_timeout=15 * 60, label="safetybuddy-gemma")
def gemma():
    model = os.environ.get("MODEL_REPO", MODEL_REPO)
    served_name = os.environ.get("VISION_MODEL", model)
    cmd = [
        "vllm", "serve", model,
        "--host", "0.0.0.0", "--port", str(VLLM_PORT),
        "--api-key", os.environ.get("LLM_API_KEY", "not-needed"),
        "--served-model-name", served_name,
        "--max-model-len", str(int(os.environ.get("MAX_MODEL_LEN", MAX_MODEL_LEN))),
        "--limit-mm-per-prompt", '{"image": 1}',     # one image per PPE request
        "--gpu-memory-utilization", "0.90",
        "--enforce-eager",                            # skip torch.compile: faster cold start, fewer JIT paths
    ]
    subprocess.Popen(cmd)


# --------------------------------------------------------------------------- #
# Web front door — the Flask app (WSGI). YOLO + nomic run here on CPU.
# --------------------------------------------------------------------------- #
def _gemma_base_url() -> str | None:
    """Resolve the in-cluster Gemma endpoint URL across Modal versions."""
    for attr in ("get_web_url", "web_url"):
        try:
            value = getattr(gemma, attr)
            base = value() if callable(value) else value
            if base:
                return base.rstrip("/") + "/v1"
        except Exception:
            continue
    return None


@app.function(
    image=web_image,
    volumes={HF_CACHE_DIR: hf_cache},
    secrets=secrets,
    cpu=2.0,                 # faster CPU YOLO for the live webcam path + nomic embeddings
    scaledown_window=300,
    timeout=900,
)
@modal.concurrent(max_inputs=50)
@modal.wsgi_app(label="safetybuddy")
def web():
    # Point the app at the Gemma endpoint (overrides any stale LLM_BASE_URL in
    # the secret). Must run before importing the app so config picks it up.
    base = _gemma_base_url()
    if base:
        os.environ["LLM_BASE_URL"] = base

    from run import app as flask_app
    return flask_app


# --------------------------------------------------------------------------- #
# Knowledge-base seeding (run once after deploy)
# --------------------------------------------------------------------------- #
@app.function(image=web_image, volumes={HF_CACHE_DIR: hf_cache}, secrets=secrets, timeout=20 * 60)
def seed() -> dict:
    from src.rag.sources import SEED_SOURCES
    from src.rag.web_ingest import ingest_urls

    return ingest_urls(SEED_SOURCES)
