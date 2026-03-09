# 🛡️ SafetyBuddy

**A Multimodal LLM-Based Safety Intelligence Platform for PPE Compliance**

SafetyBuddy combines YOLO26 real-time video detection with GPT-4o reasoning and RAG-based regulatory knowledge to provide complete PPE compliance monitoring.

Built with **Flask** + modern responsive frontend, deployable to **AWS**.

---

## Quick Start (4 Steps)

```bash
# 1. Setup
cp .env.example .env          # Add your OpenAI key to .env
pip install -r requirements.txt

# 2. Download OSHA documents
python scripts/download_data.py

# 3. Build the knowledge base
python ingest.py

# 4. Launch
python run.py
```

Opens at http://localhost:5000

---

## Detailed Setup Guide

### Prerequisites

- Python 3.9+
- OpenAI API key (GPT-4o access)
- Google Colab account (free, for YOLO26 training)

### Step 1: Environment

```bash
cd safetybuddy
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your OpenAI API key:
# OPENAI_API_KEY=sk-your-key-here
# SECRET_KEY=change-this-in-production
```

### Step 2: Data

**A) Auto-download OSHA PDFs:**
```bash
python scripts/download_data.py
```

**B) Manual: Copy regulation text** (15 minutes)

Open each URL below in your browser, select all text, save as `.txt` in `data/raw/regulations/`:

| Save As | URL |
|---------|-----|
| `osha_1910_132_general_ppe.txt` | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.132 |
| `osha_1910_133_eye_face.txt` | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.133 |
| `osha_1910_135_head.txt` | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.135 |
| `osha_1910_136_foot.txt` | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.136 |
| `osha_1910_138_hand.txt` | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.138 |

**C) SOPs and incidents** are already included in the project:
- `data/raw/manuals/SOP_001_PPE_Selection_Assessment.txt`
- `data/raw/manuals/SOP_002_PPE_Inspection_Maintenance.txt`
- `data/raw/manuals/SOP_003_Chemical_PPE_Selection.txt`
- `data/raw/incident_logs/ppe_incidents_sample.json`

### Step 3: Build Knowledge Base

```bash
python ingest.py
```

This embeds all documents into ChromaDB (~$0.01 in OpenAI API cost).

### Step 4: Train YOLO26 (for Video Monitor)

> **Note:** The Chat page works without YOLO26. Only the Video Monitor needs the trained model.

1. Download the PPE image dataset from Kaggle:
   https://www.kaggle.com/datasets/snehilsanyal/construction-site-safety-image-dataset-roboflow

2. Open Google Colab, connect to T4 GPU (free)

3. Copy each cell from `notebooks/train_yolo_ppe.py` into Colab and run them

4. Download the trained `best.pt` file

5. Save it as `data/models/ppe_yolo26n.pt`

Training takes ~2-3 hours on a free T4 GPU.

### Step 5: Launch

```bash
# Development
python run.py

# Production (with gunicorn)
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 run:app
```

Opens at http://localhost:5000

---

## Features

### 📊 Dashboard
- Real-time stats: queries, images analyzed, violations, video frames
- Recent alert log with severity indicators
- Quick actions to jump to any feature
- Auto-refreshes every 15 seconds

### 💬 Chat Page
- Ask PPE compliance questions in natural language
- Upload inspection images → YOLO26 bounding boxes + GPT-4o visual analysis
- Annotated image displayed with detection badges (compliant/violation)
- Three modes: Safety Advisor, Incident Analyst, Compliance Auditor
- Every response includes source citations and OSHA regulation traceability
- Markdown-rendered responses with typing indicators

### 📹 Video Monitor Page
- **Live Webcam:** Real-time PPE detection via browser camera → YOLO26 → annotated feed
- **Video Upload:** Analyze recorded video files for PPE violations frame-by-frame
- YOLO26 draws green boxes (compliant) and red boxes (violations) on every frame
- Adjustable FPS target and confidence threshold
- Snapshot + GPT-4o deep analysis button during live detection
- When violations are detected, GPT-4o provides detailed regulatory analysis
- Violation log with real-time alerts

### 📋 Compliance Reference Page
- Full OSHA PPE standards quick reference table
- Expandable detailed regulation sections
- Compliance tips and best practices
- Direct links to OSHA source documents

---

## Architecture

```
User → Flask Web App (http://localhost:5000)
        │
        ├── Dashboard  (/) ─────── GET /api/dashboard → Stats + Alerts
        │
        ├── Chat (/chat) ──────── POST /api/chat → RAG (ChromaDB) → GPT-4o → Response + OSHA citations
        │                          POST /api/analyze-image → YOLO26 annotations + GPT-4o Vision
        │
        ├── Monitor (/monitor)
        │   ├── Live Webcam ────── POST /api/detect-frame → YOLO26 → Annotated frame (real-time)
        │   ├── Video Upload ───── POST /api/process-video → YOLO26 (every frame)
        │   └── Deep Analysis ──── POST /api/analyze-violation → GPT-4o → Regulatory analysis
        │
        └── Compliance (/compliance) → Static OSHA reference
```

**Key design:** YOLO26 runs locally (free, ~30 FPS on CPU). GPT-4o is only called when
violations are detected or when the user requests analysis (cost-efficient).
Image analysis returns YOLO26-annotated images with bounding boxes alongside GPT-4o text.

---

## Project Structure

```
safetybuddy/
├── data/
│   ├── raw/
│   │   ├── regulations/           # OSHA PDFs + text files
│   │   ├── manuals/               # 3 sample SOPs (included)
│   │   └── incident_logs/         # 8 sample incidents (included)
│   ├── processed/                 # ChromaDB (built by ingest.py)
│   └── models/                    # ppe_yolo26n.pt (from Colab training)
├── src/
│   ├── ingestion/
│   │   ├── document_loader.py     # PDF/TXT/JSON loader
│   │   └── chunker.py            # Smart text chunking
│   ├── rag/
│   │   ├── vectorstore.py        # ChromaDB + OpenAI embeddings
│   │   └── chains.py             # 4 RAG chain modes (GPT-4o)
│   ├── vision/
│   │   ├── image_analyzer.py     # GPT-4o still image analysis
│   │   └── video_detector.py     # YOLO26 real-time detection
│   ├── compliance/
│   │   ├── regulations.py        # OSHA PPE regulation registry
│   │   └── mapper.py             # Auto-tags responses with regulations
│   └── ui/
│       ├── flask_app.py          # Flask app factory
│       ├── routes/
│       │   ├── pages.py          # Page routes (HTML views)
│       │   └── api.py            # REST API endpoints
│       ├── templates/
│       │   ├── base.html         # Base layout (sidebar, topbar)
│       │   ├── dashboard.html    # Dashboard page
│       │   ├── chat.html         # Chat interface
│       │   ├── monitor.html      # Video monitor
│       │   └── compliance.html   # Regulation reference
│       └── static/
│           ├── css/style.css     # Custom dark theme
│           └── js/app.js         # Core JavaScript
├── scripts/
│   └── download_data.py          # Auto-downloads OSHA PDFs
├── notebooks/
│   └── train_yolo_ppe.py         # Colab training script for YOLO26
├── run.py                        # Flask entry point
├── ingest.py                     # Document ingestion pipeline
├── Dockerfile                    # Container image (production)
├── docker-compose.yml            # Docker Compose config
├── deploy_ec2.sh                 # EC2 deploy script (Linux/Mac)
├── deploy_ec2.ps1                # EC2 deploy script (Windows)
├── requirements.txt
├── .env
└── README.md
```

---

## Test Queries

**Safety Advisor:**
- "What PPE is required for transferring concentrated sulfuric acid?"
- "What are OSHA requirements for hard hat inspections?"

**Incident Analyst:**
- "A worker got chemical burns handling solvents with nitrile gloves. Analyze."

**Compliance Auditor:**
- "We have no written hazard assessment. What's our compliance status?"

---

## Cost

| Component | Monthly Cost |
|-----------|-------------|
| GPT-4o text (~200 queries) | ~$5-10 |
| GPT-4o vision (~50 alerts) | ~$3-5 |
| Embeddings (one-time) | ~$0.01 |
| YOLO26 inference | Free (local) |
| YOLO26 training (Colab) | Free (T4 GPU) |
| AWS EC2 t3.small | ~$15/month |
| **Total** | **~$23-30/month** |

---

## Deployment

### Option 1: AWS EC2 (Recommended)

**Prerequisites:**
- EC2 instance (t3.small or larger, Amazon Linux 2)
- Security group with ports 22 (SSH) and 5000 (or 80) open
- SSH key pair (.pem file)

**One-command deploy:**

```bash
# Linux/Mac
chmod +x deploy_ec2.sh
./deploy_ec2.sh <ec2-public-ip> ~/.ssh/your-key.pem

# Windows PowerShell
.\deploy_ec2.ps1 -EC2Host "54.123.45.67" -KeyFile "C:\Users\you\.ssh\your-key.pem"
```

The script will:
1. Install Docker on the EC2 instance
2. Sync all project files (including the YOLO model)
3. Build the Docker image
4. Start the container with `docker compose`
5. Run a health check

**After deploy, set your OpenAI key on EC2:**
```bash
ssh -i your-key.pem ec2-user@<ec2-ip>
nano /home/ec2-user/safetybuddy/.env
# Set: OPENAI_API_KEY=sk-your-key-here
docker compose restart
```

### Option 2: Docker (any cloud/VPS)

```bash
# Clone the repo and set up .env
cp .env.example .env   # Add your OPENAI_API_KEY

# Build and run
docker compose up -d

# Check health
curl http://localhost:5000/api/health
```

### Option 3: Local Development

```bash
python run.py
# Opens at http://localhost:5000
```

---

## License

Research use. YOLO26 weights are under AGPL-3.0.
OSHA documents are US government public domain.
