<div align="center">

# 🛡️ SafetyBuddy

**A multimodal PPE-compliance platform: self-hosted Gemma 4 vision and chat, real-time YOLO26 detection, and a self-improving, citation-grounded RAG over OSHA safety regulation.**

[![Live demo](https://img.shields.io/badge/Live-app-16a34a)](https://chidi-ashinze--safetybuddy.modal.run)
[![Model](https://img.shields.io/badge/Vision%20%26%20chat-Gemma%204-4285F4)](https://huggingface.co/google/gemma-4-E4B-it)
[![Detector](https://img.shields.io/badge/Real--time-YOLO26-00b894)](https://docs.ultralytics.com/)
[![Deploy](https://img.shields.io/badge/Serverless-Modal-7c3aed)](https://modal.com/)
[![License](https://img.shields.io/badge/License-Research-blue.svg)](#license)

Built by **Chidi Ashinze** · [GitHub](https://github.com/Mystique1337/safetybuddy)

</div>

---

## What this is

SafetyBuddy watches industrial scenes for personal-protective-equipment (PPE) compliance and explains what it sees against the rules.

It pairs two complementary vision paths with a regulation-aware assistant:

- **YOLO26** runs locally on CPU and flags missing hard hats, masks, and high-vis vests in live webcam or recorded video, in real time and for free.
- **Gemma 4** (Google's open, natively multimodal model) does the careful, written inspection of an uploaded photo or a flagged frame, severity-rated and cited to the relevant OSHA standard.
- A **self-improving RAG** answers compliance questions grounded in OSHA Subpart I (29 CFR 1910.132-138). When local coverage is weak it fetches authoritative sources live (OSHA, NIOSH, EU-OSHA, HSE), ingests them, and re-answers, so the knowledge base keeps growing as the app is used.

Everything runs on the user's own infrastructure: Gemma 4 is served by vLLM on a single Modal GPU (scale-to-zero), and the knowledge base, alerts, and analytics live in a self-hosted Supabase (Postgres + pgvector). There is no dependency on a third-party LLM API.

Live app: **https://chidi-ashinze--safetybuddy.modal.run**

## Features

- **Real-time PPE detection.** YOLO26 NMS-free inference draws compliant (green) and violation (red) boxes on a live webcam feed or an uploaded video, with adjustable FPS target and confidence threshold. Violations are logged as alerts.
- **Gemma 4 visual inspection.** Upload an inspection photo and get a systematic head-to-toe PPE check (head, eye/face, hand, foot, body, hearing, respiratory, hazards), each finding severity-rated and tied to an OSHA standard, with an overall risk level.
- **Self-improving, cited RAG.** Hybrid retrieval (dense pgvector plus Postgres full-text, fused with Reciprocal Rank Fusion) over an OSHA knowledge base. Weak coverage triggers a live fetch from authoritative safety domains; a background job keeps enriching after every query. Answers carry source citations and OSHA traceability.
- **Four assistant modes.** Safety Advisor, Incident Analyst, Compliance Auditor, and a concise real-time Video-Alert mode for flagged frames.
- **Durable state.** Alerts, usage analytics, and answer feedback persist in Supabase (they survive restarts), and power the dashboard counters.
- **Cost controlled.** One GPU only (hard-capped), CPU embeddings and CPU YOLO, fast scale-down, scale to zero when idle.
- **One-command deploy.** GitHub Actions deploys to Modal on every push to master.

## Architecture

```
Browser ──> Flask web app (Modal, WSGI)
              │
              ├─ Dashboard  (/)            GET  /api/dashboard     counters + recent alerts (Supabase)
              │
              ├─ Chat (/chat)              POST /api/chat          self-improving RAG -> Gemma 4 -> cited answer
              │                            POST /api/analyze-image YOLO26 boxes + Gemma 4 written inspection
              │
              ├─ Monitor (/monitor)
              │   ├─ Live webcam           POST /api/detect-frame      YOLO26 (CPU), per-frame annotation
              │   ├─ Video upload          POST /api/process-video     YOLO26 over sampled frames
              │   └─ Deep analysis         POST /api/analyze-violation Gemma 4 regulatory analysis of a frame
              │
              └─ Compliance (/compliance)  static OSHA reference

   Gemma 4 (vLLM, OpenAI-compatible)  ──  one L4 GPU on Modal, scale-to-zero, bearer-key protected
   Knowledge base + analytics         ──  self-hosted Supabase (Postgres + pgvector), schema "safety_buddy"
   Embeddings                         ──  nomic-embed-text-v1.5 on CPU, in the web container
```

### How a chat query flows

1. Embed the query with `nomic-embed-text-v1.5` (CPU) and run hybrid retrieval over Supabase pgvector (dense vectors plus full-text, fused with RRF).
2. Score local coverage. If the top similarity is below `RAG_COVERAGE_THRESHOLD` or there are too few hits, fetch authoritative sources live (Tavily search biased to safety domains, or the curated seed list), clean them (trafilatura for HTML, PyMuPDF for PDF), chunk, embed, upsert with SHA-256 dedup, then re-retrieve.
3. Gemma 4, served by vLLM on Modal, answers in the requested mode with inline OSHA citations.
4. The turn is logged to Supabase analytics, and a background thread tops the knowledge base up for next time.

### Stack

`Modal` (serverless GPU) · `vLLM` · `Gemma 4` (E4B, multimodal) · `YOLO26` / Ultralytics · `Flask` (WSGI) · self-hosted `Supabase` + `pgvector` · `nomic-embed-text-v1.5` · `trafilatura` / `PyMuPDF` · optional `Tavily`.

## Repository layout

```
safetybuddy/
├── modal_app.py            Modal entrypoint (Gemma 4 vLLM GPU + Flask web + seed job)
├── run.py                  Flask entry point (local dev)
├── ingest.py               Ingest local OSHA files into Supabase pgvector
├── src/
│   ├── config.py           Env-driven settings (model, Supabase, RAG tuning)
│   ├── llm.py              OpenAI-compatible client pointed at the Gemma endpoint
│   ├── db.py              Shared psycopg pool (search_path = safety_buddy)
│   ├── vision/
│   │   ├── image_analyzer.py   Gemma 4 still-image PPE inspection
│   │   └── video_detector.py   YOLO26 real-time detection
│   ├── rag/
│   │   ├── embeddings.py       nomic embeddings (CPU)
│   │   ├── vectorstore.py      pgvector hybrid search + chunk upserts
│   │   ├── retriever.py        coverage-gated, self-improving retrieval
│   │   ├── web_ingest.py       fetch -> clean -> chunk -> embed -> upsert (dedup/TTL)
│   │   ├── sources.py          curated authoritative sources + web-search bias
│   │   └── chains.py           four RAG chat modes (Gemma 4)
│   ├── compliance/             OSHA regulation registry + response auto-tagging
│   ├── storage/db.py           alerts / usage / feedback (Supabase, in-memory fallback)
│   └── ui/                      Flask factory, routes, templates, static
├── supabase/schema.sql     pgvector KB + hybrid_search RPCs + analytics tables (safety_buddy schema)
├── scripts/
│   ├── setup_supabase.sh       apply schema.sql
│   ├── setup_modal_secret.sh   build the Modal secret from .env
│   └── seed_kb.py              seed the KB with curated authoritative sources
├── notebooks/train_yolo_ppe.py Colab training script for the YOLO26 detector
├── .github/workflows/deploy-modal.yml   CI/CD: deploy to Modal on push to master
├── .env.example
└── requirements.txt
```

## Quick start (local)

```bash
git clone https://github.com/Mystique1337/safetybuddy.git
cd safetybuddy
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in the values below
```

The app boots with no database (in-memory state, empty knowledge base) so the UI works immediately:

```bash
python run.py                   # http://localhost:6768
```

For the full experience locally, point `.env` at your Supabase and a Gemma endpoint (a local vLLM, or the deployed Modal URL), then seed the knowledge base:

```bash
bash scripts/setup_supabase.sh  # create the safety_buddy schema
python scripts/seed_kb.py       # fetch + embed the curated OSHA sources
# (optional) also ingest the bundled local OSHA files:
python ingest.py
```

## Self-hosted Supabase setup

SafetyBuddy keeps all of its tables in their own Postgres schema (`SUPABASE_DB_SCHEMA`, default `safety_buddy`) so they never collide with other apps on the same instance.

```bash
# .env: set SUPABASE_DB_URL to your direct Postgres connection string
bash scripts/setup_supabase.sh
# or paste supabase/schema.sql into the Supabase SQL editor
```

This creates `kb_chunks` (HNSW + full-text indexed), the `match_chunks` / `hybrid_search` / `kb_stats` functions, `kb_sources` (dedup + freshness), and the `events` / `alerts` / `feedback` analytics tables, all in `safety_buddy`. The embedding dimension is 768 (nomic); change every `vector(768)` if you switch `EMBED_MODEL`.

## Deploy to Modal

The whole app (Gemma 4 GPU service + Flask web) is one `modal_app.py`.

```bash
# 1. Authenticate (uses the chidi-ashinze workspace)
modal profile activate chidi-ashinze

# 2. Push runtime config (.env) into a Modal secret
bash scripts/setup_modal_secret.sh        # creates "safetybuddy-secrets"

# 3. Deploy
modal deploy modal_app.py
#   web:   https://chidi-ashinze--safetybuddy.modal.run
#   gemma: https://chidi-ashinze--safetybuddy-gemma.modal.run/v1  (vLLM, bearer-key protected)

# 4. Seed the knowledge base on the deployed infra (uses the same secret)
modal run modal_app.py::seed
```

`gemma` serves Gemma 4 (E4B) on a single L4 GPU and scales to zero when idle; the web container resolves its URL automatically and injects it as `LLM_BASE_URL`. To use a higher-quality variant, set `MODEL_REPO=google/gemma-4-26B-A4B-it`, `LLM_GPU=A100`, and matching `VISION_MODEL` / `CHAT_MODEL`.

### CI/CD

`.github/workflows/deploy-modal.yml` deploys on every push to master. Add two repository secrets (Settings -> Secrets and variables -> Actions): `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` for the target workspace. Runtime config stays in the Modal `safetybuddy-secrets` bundle, so CI never sees `.env`.

## Configuration

All settings live in `.env` (see `.env.example` for the full list). The essentials:

| Variable | Purpose |
|---|---|
| `MODEL_REPO` / `LLM_GPU` | Gemma 4 variant served by vLLM and its GPU (`google/gemma-4-E4B-it` on `L4`). |
| `LLM_BASE_URL` / `LLM_API_KEY` | Gemma OpenAI-compatible endpoint and its bearer key (set automatically on Modal). |
| `VISION_MODEL` / `CHAT_MODEL` | Model names the app requests (must match what vLLM serves). |
| `SUPABASE_DB_URL` / `SUPABASE_DB_SCHEMA` | Direct Postgres URL and the dedicated schema (`safety_buddy`). |
| `EMBED_MODEL` / `EMBED_DIM` | Embedding model and dimension (`nomic-embed-text-v1.5`, 768). |
| `RAG_COVERAGE_THRESHOLD` / `RAG_MIN_CHUNKS` | When to consider local coverage weak and fetch live. |
| `RAG_ALWAYS_ENRICH` / `RAG_ENRICH_MAX_URLS` / `RAG_DOC_TTL_DAYS` | Background enrichment, sources per weak query, refresh interval. |
| `TAVILY_API_KEY` | Optional live web search biased to authoritative safety domains (falls back to curated seeds). |

## API reference

`POST /api/chat`, `POST /api/analyze-image`, `POST /api/process-video`, `POST /api/detect-frame`, `POST /api/analyze-violation`, `POST /api/feedback`, `GET /api/dashboard`, `GET /api/alerts`, `GET /api/kb/stats`, `GET /api/model-status`, `GET /api/health`.

## Knowledge base and the self-improving RAG

The knowledge base starts from the curated authoritative sources in `src/rag/sources.py` (OSHA 1910.132-138, OSHA PPE and respiratory protection, EU-OSHA, HSE, NIOSH/Wikipedia) plus the bundled local OSHA files. From there it grows on its own: weak queries pull fresh authoritative pages in, and a background job keeps topping it up. `kb_sources` tracks every ingested URL with a content hash and timestamp, so sources are de-duplicated and re-fetched only after `RAG_DOC_TTL_DAYS`.

## Training the detector

The PPE detector ships with the repo (`data/models/ppe_yolo26n.pt`). To retrain on the [construction-site safety dataset](https://www.kaggle.com/datasets/snehilsanyal/construction-site-safety-image-dataset-roboflow), run `notebooks/train_yolo_ppe.py` on a free Colab T4 and drop the resulting weights at `data/models/ppe_yolo26n.pt`.

## Cost

| Component | Cost |
|---|---|
| Gemma 4 (E4B) on Modal L4 | Pay-per-second, scales to zero when idle |
| YOLO26 inference | Free (CPU, in the web container) |
| nomic embeddings | Free (CPU) |
| Supabase (self-hosted) | Your own infrastructure |
| Web container | Pennies; scales to zero |

One GPU at most, idle to zero: you pay for GPU time only while Gemma is actually answering.

## License

Research use. YOLO26 / Ultralytics weights are under AGPL-3.0. Gemma 4 is under the Apache-2.0 license. OSHA documents are US government public domain.
