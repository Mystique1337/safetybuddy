<div align="center">

# 🦺 SafetyBuddy

### AI-powered PPE compliance for industrial sites

**Catch missing protective equipment in real time, understand exactly what is wrong, and back every answer with the right OSHA standard. All on your own infrastructure.**

[![Live demo](https://img.shields.io/badge/▶_Live_app-FACC15?style=for-the-badge&labelColor=111114)](https://chidi-ashinze--safetybuddy.modal.run)

[![Gemma 4](https://img.shields.io/badge/Vision_&_chat-Gemma_4-4285F4)](https://huggingface.co/google/gemma-4-E4B-it)
[![YOLO26](https://img.shields.io/badge/Real--time-YOLO26-00B894)](https://docs.ultralytics.com/)
[![Modal](https://img.shields.io/badge/Serverless_GPU-Modal-7C3AED)](https://modal.com/)
[![Supabase](https://img.shields.io/badge/Vector_store-Supabase_pgvector-3ECF8E)](https://supabase.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Research-blue.svg)](#license)

`ppe` · `safety` · `osha` · `computer-vision` · `yolo` · `gemma` · `multimodal` · `vlm` · `rag` · `vllm` · `modal` · `supabase` · `pgvector` · `flask`

Built by **Chidi Ashinze** · [GitHub](https://github.com/Mystique1337/safetybuddy) · **[chidi-ashinze--safetybuddy.modal.run](https://chidi-ashinze--safetybuddy.modal.run)**

</div>

---

## What it is

SafetyBuddy watches industrial scenes for personal protective equipment (PPE) and explains what it sees against the rules. It is built for the people on the ground: safety officers, supervisors, and crews, not engineers. The interface is a bold, hi-vis industrial console, and the AI plumbing stays out of the way.

It combines three things:

- **Detect.** YOLO26 runs on CPU and flags missing hard hats, hi-vis vests, and masks in a live webcam or recorded video, in real time and for free.
- **Inspect.** Gemma 4, Google's open natively-multimodal model, writes a careful, severity-rated PPE report for any flagged frame or uploaded photo, cited to the relevant OSHA standard.
- **Comply.** A self-improving knowledge base answers compliance questions grounded in OSHA Subpart I (29 CFR 1910.132-138). When local coverage is weak it pulls authoritative sources in live (OSHA, NIOSH, EU-OSHA, HSE), learns them, and re-answers, so it gets sharper the more it is used.

Everything runs on your own infrastructure. Gemma 4 is served by vLLM on a single Modal GPU that scales to zero, and the knowledge base, alerts, analytics, and subscribers live in a self-hosted Supabase (Postgres + pgvector). There is no dependency on a third-party LLM API.

> Live app: **https://chidi-ashinze--safetybuddy.modal.run**

## Features

**Live monitoring console**
- Always-on detection stage with a STANDBY state and a one-tap Start Camera.
- A HUD viewfinder (yellow corner brackets) and smooth video: a render loop draws the webcam at full frame rate while detections overlay on top.
- A loud violation moment: the whole stage flashes red, a banner names the missing PPE, an optional alert beep fires, and a one-tap **Explain** runs the AI report on that exact frame.
- Upload a recorded video and every frame is scanned, with violation snapshots and optional AI analysis.

**Photo inspection**
- Upload an inspection photo and get a clean **PPE report card**: an At risk / Compliant verdict, a worker count, and a checklist (Hard hat, Hi-vis vest, Mask: OK / Missing / Not detected), with the full AI inspection one click away.

**Safety advisor**
- Ask any PPE question and get an answer grounded in OSHA regulation with inline citations and source links. Four modes: Safety Advisor, Incident Analyst, Compliance Auditor, and a concise real-time Video Alert mode.

**Dashboard and records**
- Safety KPIs (Violations today, Violations all time, Inspections run, Questions answered), a live alerts feed, and recent activity, all persisted in Supabase so nothing is lost on restart.
- An optional, dismissible email capture for product updates (opt-in only, never blocks anything).

**Built to run cheaply**
- One GPU at most (hard-capped), scale-to-zero when idle, CPU detection and CPU embeddings. You pay for GPU time only while the model is actually answering.

## How it works

**A live frame**
1. The browser captures a webcam frame, downscales it, and posts it to the server.
2. YOLO26 detects PPE classes on CPU and returns boxes.
3. The browser overlays the boxes on the smooth local video; a violation lights the stage red, logs an alert to Supabase, and can run a Gemma 4 explanation.

**A question or photo**
1. The query is embedded with `nomic-embed-text-v1.5` (CPU) and hybrid-retrieved over Supabase pgvector (dense vectors plus Postgres full-text, fused with Reciprocal Rank Fusion).
2. If local coverage is weak, authoritative sources are fetched live, cleaned, chunked, embedded, de-duplicated, and re-retrieved.
3. Gemma 4 (served by vLLM on Modal) answers with inline OSHA citations, or inspects the image and returns a report card.
4. The turn is logged to Supabase, and a background job keeps growing the knowledge base.

## Architecture

```
Browser ──> Flask web app (Modal, WSGI, bold hi-vis UI)
              │
              ├─ Dashboard   safety KPIs + alerts feed        (Supabase)
              ├─ Monitor     YOLO26 (CPU) live + video         -> alerts, AI explain
              ├─ Chat        self-improving RAG -> Gemma 4      -> cited report card
              └─ Compliance  OSHA Subpart I reference

   Gemma 4 (vLLM, OpenAI-compatible)  ── one L4 GPU on Modal, scale-to-zero, bearer-key protected
   Knowledge base + analytics + subs  ── self-hosted Supabase (Postgres + pgvector), schema safety_buddy
   Embeddings                         ── nomic-embed-text-v1.5 on CPU, in the web container
```

### Stack

`Modal` (serverless GPU) · `vLLM` · `Gemma 4` (E4B, multimodal) · `YOLO26` / Ultralytics · `Flask` (WSGI) · self-hosted `Supabase` + `pgvector` · `nomic-embed-text-v1.5` · `trafilatura` / `PyMuPDF` · optional `Tavily` · `Bootstrap 5` + custom industrial CSS.

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
│   │   ├── web_ingest.py       fetch -> clean -> chunk -> embed -> upsert
│   │   ├── sources.py          curated authoritative sources + web-search bias
│   │   └── chains.py           four RAG chat modes (Gemma 4)
│   ├── compliance/             OSHA regulation registry + response auto-tagging
│   ├── storage/db.py           alerts / usage / feedback / subscribers (Supabase + in-memory fallback)
│   └── ui/                      Flask factory, routes, templates, static (industrial design system)
├── supabase/schema.sql     pgvector KB + hybrid_search RPCs + analytics + subscribers (safety_buddy schema)
├── scripts/
│   ├── setup_supabase.sh       apply schema.sql
│   ├── setup_modal_secret.sh   build the Modal secret from .env
│   ├── seed_kb.py              seed the KB with curated authoritative sources
│   └── export_subscribers.py   export opt-in emails to CSV
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
cp .env.example .env            # fill in the values (see Configuration)
python run.py                   # http://localhost:6768
```

The app boots with no database (in-memory state, empty knowledge base), so the UI works immediately. For the full experience, point `.env` at your Supabase and a Gemma endpoint, then seed the knowledge base:

```bash
bash scripts/setup_supabase.sh  # create the safety_buddy schema
python scripts/seed_kb.py       # fetch + embed the curated OSHA sources
python ingest.py                # (optional) also ingest the bundled local OSHA files
```

## Self-hosted Supabase

Every SafetyBuddy table lives in its own Postgres schema (`SUPABASE_DB_SCHEMA`, default `safety_buddy`) so it never collides with other apps on the same instance.

```bash
# set SUPABASE_DB_URL in .env, then:
bash scripts/setup_supabase.sh   # or paste supabase/schema.sql into the Supabase SQL editor
```

This creates `kb_chunks` (HNSW + full-text indexed), the `match_chunks` / `hybrid_search` / `kb_stats` functions, `kb_sources` (dedup + freshness), and the `events` / `alerts` / `feedback` / `subscribers` tables. The embedding dimension is 768 (nomic); change every `vector(768)` if you switch `EMBED_MODEL`.

## Deploy to Modal

The whole app (Gemma 4 GPU service + Flask web) is one `modal_app.py`.

```bash
modal profile activate chidi-ashinze
bash scripts/setup_modal_secret.sh        # create the secret bundle from .env
modal deploy modal_app.py
#   web:   https://chidi-ashinze--safetybuddy.modal.run
#   gemma: https://chidi-ashinze--safetybuddy-gemma.modal.run/v1  (vLLM, bearer-key protected)
modal run modal_app.py::seed              # seed the KB on the deployed infra
```

`gemma` serves Gemma 4 (E4B) on a single L4 GPU and scales to zero when idle; the web container resolves its URL automatically and injects it as `LLM_BASE_URL`. For a higher-quality variant set `MODEL_REPO=google/gemma-4-26B-A4B-it`, `LLM_GPU=A100`, and matching `VISION_MODEL` / `CHAT_MODEL`.

**Deploy note.** The web app is a long-lived WSGI process that imports the code once at container start, so a plain redeploy may keep serving old code from a warm container. If a change does not seem to go live, force a clean restart:

```bash
modal app stop safetybuddy --yes && modal deploy modal_app.py
```

### CI/CD

`.github/workflows/deploy-modal.yml` deploys on every push to master. Add two repository secrets: `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`. Runtime config stays in the Modal `safetybuddy-secrets` bundle, so CI never sees `.env`.

## Configuration

All settings live in `.env` (see `.env.example`). The essentials:

| Variable | Purpose |
|---|---|
| `MODEL_REPO` / `LLM_GPU` | Gemma 4 variant and its GPU (`google/gemma-4-E4B-it` on `L4`). |
| `LLM_BASE_URL` / `LLM_API_KEY` | Gemma OpenAI-compatible endpoint and its bearer key (auto-set on Modal). |
| `VISION_MODEL` / `CHAT_MODEL` | Model names the app requests (must match what vLLM serves). |
| `SUPABASE_DB_URL` / `SUPABASE_DB_SCHEMA` | Direct Postgres URL and the dedicated schema (`safety_buddy`). |
| `EMBED_MODEL` / `EMBED_DIM` | Embedding model and dimension (`nomic-embed-text-v1.5`, 768). |
| `RAG_COVERAGE_THRESHOLD` / `RAG_MIN_CHUNKS` | When to consider local coverage weak and fetch live. |
| `RAG_ALWAYS_ENRICH` / `RAG_ENRICH_MAX_URLS` / `RAG_DOC_TTL_DAYS` | Background enrichment, sources per weak query, refresh interval. |
| `TAVILY_API_KEY` | Optional live web search biased to authoritative safety domains. |

## API reference

`POST /api/chat` · `POST /api/analyze-image` · `POST /api/process-video` · `POST /api/detect-frame` · `POST /api/analyze-violation` · `POST /api/feedback` · `POST /api/subscribe` · `GET /api/dashboard` · `GET /api/alerts` · `GET /api/kb/stats` · `GET /api/model-status` · `GET /api/health`

## Cost

| Component | Cost |
|---|---|
| Gemma 4 (E4B) on Modal L4 | Pay-per-second, scales to zero when idle |
| YOLO26 detection + nomic embeddings | Free (CPU, in the web container) |
| Supabase (self-hosted) | Your own infrastructure |
| Web container | Pennies; scales to zero |

## License

Research use. YOLO26 / Ultralytics weights are under AGPL-3.0. Gemma 4 is under the Apache-2.0 license. OSHA documents are US government public domain.
