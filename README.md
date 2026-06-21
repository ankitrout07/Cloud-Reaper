# ☁️ Cloud-Reaper

[![CI](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)
![Go](https://img.shields.io/badge/Go-1.24%2B-00ADD8?logo=go)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A high-performance **Hybrid FinOps Intelligence Engine** designed to bridge the gap between cloud financial management and automated engineering action.

Cloud-Reaper uses a **Dual-Core Architecture** (Python + Go) to achieve massive scanning speeds across large-scale multi-cloud environments. It provides real-time cost reduction recommendations, regional price arbitrage, Q-learning right-sizing, ARIMA budget forecasting, automated governance enforcement, cryptographically signed audit trails, and a **Cost-Bounded Performance Copilot** powered by Google Gemini 2.5 Flash.

---

## Table of Contents

- [Key Features](#-key-features)
- [Hybrid Architecture](#-hybrid-architecture)
- [Project Structure](#-project-structure)
- [Tech Stack](#-tech-stack)
- [Getting Started](#-getting-started)
- [Docker Deployment](#-docker-deployment)
- [Intelligence & ML Models](#-intelligence--ml-models)
- [Cost-Bounded Performance Copilot](#-cost-bounded-performance-copilot)
- [RAG Documentation Search](#-rag-documentation-search)
- [Cryptographic Audit Trails](#-cryptographic-audit-trails)
- [Vault & Secret Management](#-vault--secret-management)
- [Multi-Cloud Provider Support](#-multi-cloud-provider-support)
- [Database Schema](#-database-schema)
- [API Reference](#-api-reference)
- [CI/CD Pipeline](#-cicd-pipeline)
- [Development Commands](#-development-commands)
- [Configuration](#-configuration)
- [Changelog](#-changelog)
- [Contributing](#-contributing)

---

## 🚀 Key Features

### 📊 Phase 1 — Inform: Visibility & High-Performance Discovery

| Feature | Description |
|---|---|
| **⚡ High-Velocity Go Scanner** | Custom Go engine with goroutines and token-bucket rate limiting (10 req/s) for sub-second Azure resource auditing |
| **🚀 In-Memory Cache** | Thread-safe global memory caching (`threading.Lock`) with custom TTLs for sub-millisecond dashboard rendering |
| **🏷️ Hierarchical Virtual Tagging** | Builds nested logical metadata tags to map costs to internal business taxonomies without altering cloud tags |
| **🧠 Unified AI/LLM Token Tracking** | Connects to AI providers (OpenAI, Google Gemini) to track generative AI billing alongside infrastructure costs |
| **🏷️ Tag Health Score** | Automated audit of critical tags (`owner`, `project`) for 100% cost attribution |
| **📈 ARIMA Anomaly Detection** | Seasonal-aware ARIMA(1,1,1) time-series forecasting with Z-score residual analysis (threshold Z=3.0) |
| **🌍 Regional Price Intelligence** | Lazy-cached Azure/AWS/GCP SKU pricing per region via `RegionPriceCache` (PostgreSQL) |
| **📡 InfluxDB Telemetry Bridge** | Pushes savings and unit economics metrics into InfluxDB for long-term time-series retention |

### 📉 Phase 2 — Optimize: Waste & Carbon Reduction

| Feature | Description |
|---|---|
| **📦 Cluster Bin-Packing** | MostAllocated strategy — drains nodes with <20% CPU density, migrating pods to denser nodes |
| **💤 Zero-Downtime Hibernation** | Scales non-production clusters to zero during off-hours, instant spin-up on developer request |
| **🌱 GreenOps Carbon Index** | Live Regional Grid Carbon Intensity estimation (gCO2eq/kWh) with green migration recommendations |
| **🧟 Zombie Hunting** | Heuristic scoring (0–100): unattached disk = +50, <10 IOPS for 7 days = +45; flagged at score ≥ 90 |
| **💎 RI/SP Advisor** | Recommends Reserved Instances and Savings Plans based on actual uptime and inventory patterns |
| **❄️ Cold Storage Identifier** | Scans unused storage and suggests cost-efficient Cool/Archive tier migrations |
| **🤖 AI Regional Arbitrage** | Concurrent worker pool (10 goroutines) for real-time cross-region SKU price comparison |
| **🧠 Cost-Bounded Copilot** | Bounded Knapsack Optimizer backed by **Gemini 2.5 Flash** with 128-entry LRU cache |
| **✨ AI Anomaly Triage** | One-click playbook generation using Gemini to automatically investigate and triage cost deviations |
| **🎮 RL Right-Sizing Agent** | Q-learning agent (α=0.1, γ=0.9) with 81-state space (3⁴) across CPU/Mem/IOPS/Network dimensions |
| **📊 Predictive Scaling** | ARIMA(1,1,0) 15-step forecast — triggers PRE_WARM at >85%, SCALE_DOWN at <20% predicted load |

### ⚖️ Phase 3 — Operate: Governance & Security

| Feature | Description |
|---|---|
| **🛑 Shift-Left Cost Simulation** | `--pr-simulation` CLI mode generates Markdown cost delta tables for GitHub PR comments |
| **🛡️ Policy Guardrails** | Real-time audit against FinOps best practices via Azure Resource Graph |
| **🚨 Budget Kill-Switch** | Automated VM deallocation for sandbox environments on budget breach |
| **🔔 Multi-Channel Alerting** | Webhook-driven alerts via Discord, Slack, and Microsoft Teams |
| **📄 PDF BOM Export** | One-click Bill of Materials export from the AI Architect Estimator (WeasyPrint) |
| **💼 Commitment Tracking** | Centralized tracking of Savings Plans and Reserved Instances across AWS and Azure |
| **☸️ Kubernetes Agent** | Connection monitoring for container cost allocation and cluster bin-packing |
| **🔐 Cryptographic Audit Trails** | SHA-256 chained hash ledger for tamper-proof action log verification |
| **🔑 Encrypted Vault** | PBKDF2-HMAC-SHA256 (600K iterations) + Fernet (AES-128-CBC) encryption with auto-lock TTL |

---

## 🏗️ Hybrid Architecture

```
                              ┌──────────────────────────────────────┐
                              │    Multi-Cloud Providers             │
                              │  Azure · AWS · GCP · Kubernetes      │
                              └────────────────┬─────────────────────┘
                                               │  SDKs / REST APIs
                          ┌────────────────────▼────────────────────┐
                          │   Go Performance Core (engine-go)       │
                          │   ├── azure_scraper  (ARM + Monitor)    │
                          │   ├── aws_scraper    (EC2 + EBS + S3)   │
                          │   ├── gcp_scraper    (Compute + GKE)    │
                          │   ├── k8s_scraper    (Metrics API)      │
                          │   ├── k8s_optimizer  (Bin-Packing)      │
                          │   ├── network_scraper (NSG + Cross-AZ)  │
                          │   ├── price_client   (23 Azure SVCs)    │
                          │   ├── arbitrage      (Region Pricing)   │
                          │   ├── auth           (Graph API)        │
                          │   ├── serve          (HTTP Bridge)      │
                          │   └── db bridge      (Zero-alloc Pool)  │
                          └────────────────────┬────────────────────┘
                                               │  PostgreSQL 15
                          ┌────────────────────▼────────────────────┐
                          │   Python Intelligence Layer             │
                          │   ├── collectors/  Azure, AWS, GCP      │
                          │   ├── engine/      ARIMA, Q-RL, Econ    │
                          │   ├── rag/         BM25 + Gemini RRF    │
                          │   ├── services/    InfluxDB, Pusher     │
                          │   └── web/         FastAPI + Uvicorn    │
                          └────────────────────┬────────────────────┘
                                               │
                          ┌────────────────────▼────────────────────┐
                          │   FastAPI ASGI Dashboard                │
                          │   ├── Real-time WebSocket metrics       │
                          │   ├── Glassmorphism Dark Theme UI       │
                          │   ├── Vault & Credential Management     │
                          │   └── http://localhost:5001             │
                          └─────────────────────────────────────────┘
```

### Data Flow

1. **Go Scanner** concurrently scrapes multi-cloud APIs using goroutines with a token-bucket rate limiter (10 req/s)
2. Resource data is normalized and batch-upserted into PostgreSQL via `pgx/v5` using a **zero-allocation `sync.Pool` buffer** (eliminates GC pauses); stale entries auto-purged after 5 min
3. **Python Intelligence Layer** queries the DB, runs ARIMA anomaly detection, Q-learning right-sizing, and unit economics models
4. **FastAPI Dashboard** calls the Go engine via a resident **HTTP bridge (loopback:7070)** for zero-fork overhead and renders real-time metrics via WebSockets with in-memory cache acceleration
5. Every vault access and resource action is logged into a **SHA-256 chained hash ledger** for tamper detection
6. Savings telemetry is pushed to **InfluxDB** for long-term time-series retention

---

## 📂 Project Structure

```text
Cloud-Reaper/
├── bin/                        # Compiled Go binaries (reaper-engine)
├── bootstrap.py                # Universal cross-platform one-click setup script
├── main.py                     # CLI entry point
├── Makefile                    # Developer shortcuts (install, build, test, lint, fmt)
├── Dockerfile                  # Multi-stage Docker build (Go builder → Python runtime)
├── docker-compose.yml          # Full-stack deployment (app + PostgreSQL)
├── pyproject.toml              # Ruff, Mypy, Pytest configuration
├── requirements.txt            # Runtime dependencies (grouped by category)
├── requirements-dev.txt        # Dev/CI dependencies (Ruff, Mypy, Pytest, Bandit)
├── HOW_TO_RUN.md               # Full setup guide
├── scripts/
│   └── reap.sh                 # Linux/macOS shell entrypoint
├── docs/                       # Project documentation (indexed by RAG engine)
│   ├── 1_product_docs.md
│   ├── 2_features_guide.md
│   ├── 4_audit_logs.md
│   ├── 5_executive_summary_and_architecture.txt
│   ├── 6_finops_intelligence_layer_python.txt
│   ├── 7_performance_scanner_go.txt
│   ├── 8_ai_copilot_and_token_usage.txt
│   └── 9_database_schema_and_api_endpoints.txt
├── CHANGELOG.md                # Release history (canonical changelog)
├── src/
│   ├── reaper/                 # Python Intelligence & Web Layer
│   │   ├── cli.py              # CLI runner (scan, --pr-simulation mode)
│   │   ├── collectors/         # Multi-cloud scrapers & price clients
│   │   │   ├── providers/            # Cloud resource collectors (Azure, etc.)
│   │   │   ├── prices/               # Azure/AWS/GCP pricing API clients
│   │   │   ├── telemetry/            # Prometheus metric bridge
│   │   │   └── utils/                # Config management & auth checks
│   │   ├── engine/             # FinOps models, ML/RL engines, economics
│   │   │   ├── core/                 # Architect, calculator, logic, economics
│   │   │   ├── copilot/              # KnapsackCopilotEngine (Gemini 2.5 Flash)
│   │   │   ├── models/               # SQLAlchemy ORM (13 tables)
│   │   │   ├── notifications/        # Multi-channel notification dispatcher
│   │   │   ├── telemetry/            # Metrics analysis & CLI
│   │   │   └── price_book.yaml       # Static SKU price reference book
│   │   ├── rag/                # Retrieval-Augmented Generation engine
│   │   │   └── engine.py             # BM25 + Gemini Embedding hybrid search + RRF
│   │   ├── services/           # Background services
│   │   │   ├── log_streamer.py       # WebSocket log streaming service
│   │   │   └── pusher.py             # InfluxDB push & notification service
│   │   └── web/                # FastAPI app, templates, static assets
│   │       ├── app_async.py          # Main FastAPI application
│   │       ├── copilot_router.py     # /api/v1/copilot/optimize
│   │       ├── metrics_router.py     # /api/metrics/*
│   │       ├── search_router.py      # /api/v1/docs/search
│   │       ├── vault_crypto.py       # PBKDF2 + Fernet encryption helpers
│   │       ├── templates/            # Jinja2 templates (15 pages)
│   │       └── static/              # CSS (Glassmorphism Dark Theme), JS, assets
│   └── engine-go/              # Go High-Velocity Performance Core
│       ├── main.go                   # Entry point & scanner orchestration
│       ├── arbitrage.go              # Concurrent regional price arbitrage scanner
│       ├── collectors/               # Multi-cloud resource scrapers
│       │   ├── azure_scraper.go      # Azure ARM resource scanner
│       │   ├── aws_scraper.go        # AWS EC2/EBS/S3 scanner
│       │   ├── gcp_scraper.go        # GCP Compute/GKE scanner
│       │   ├── k8s_scraper.go        # Kubernetes Metrics API scanner
│       │   ├── k8s_optimizer.go      # MostAllocated bin-packing optimizer
│       │   ├── network_scraper.go    # NSG + cross-AZ transit audit scanner
│       │   ├── price_client.go       # Azure Retail Pricing API client
│       │   ├── consts.go             # Shared constants
│       │   ├── auth.go               # Microsoft Graph user identity
│       │   └── provider.go           # CloudProvider interface (Authenticate / ScanResources)
│       ├── models/
│       │   └── resource.go           # Shared Go resource model
│       └── db/
│           └── db.go                 # PostgreSQL bridge (pgx/v5) + crypto audit
├── tests/
│   ├── unit/                   # Python unit tests
│   └── integration/            # Integration tests (requires live DB)
└── .github/
    └── workflows/
        └── ci.yml              # 7-stage parallel CI pipeline
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Language (Python)** | Python 3.12+ |
| **Language (Go)** | Go 1.24+ |
| **Database** | PostgreSQL 15 (SQLAlchemy 2.0 ORM + pgx/v5 driver) |
| **Time-Series** | InfluxDB (savings & unit economics telemetry via `influxdb-client`) |
| **Web Framework** | FastAPI + Uvicorn (ASGI) + WebSockets |
| **AI Copilot** | Google GenAI (`google-genai`) · Gemini 2.5 Flash · Bounded Knapsack Optimizer |
| **AI Architect** | OpenAI (`openai>=1.50.0`) + Google Gemini (multi-provider BOM generation + offline fallback) |
| **RAG Search** | BM25 sparse retrieval + Gemini Embedding dense retrieval + Reciprocal Rank Fusion (k=60) |
| **ML / Forecasting** | `statsmodels` (ARIMA, seasonal decomposition) · `scikit-learn` (GradientBoosting, regression) |
| **RL Agent** | `stable-baselines3` + `gymnasium` (Q-learning right-sizing, 81-state space) |
| **Data Science** | `numpy` · `pandas` · `scipy` · `pyarrow` |
| **Frontend** | HTML5, Vanilla JS, CSS (Glassmorphism Dark Theme, Adaptive Light/Dark Mode) |
| **Charting** | Chart.js (real-time WebSocket-driven telemetry graphs) |
| **PDF Export** | WeasyPrint |
| **Encryption** | PBKDF2-HMAC-SHA256 (600K iterations, passcode verification) + Fernet (AES-128-CBC) |
| **Audit Security** | SHA-256 chained hash ledger (blockchain-inspired tamper detection) |
| **Python Quality** | Ruff · Mypy · Pytest · Bandit · Safety |
| **Go Quality** | Golangci-lint · go test · go vet |
| **Containerization** | Docker (multi-stage build) · Docker Compose |
| **CI/CD** | GitHub Actions (7-stage parallel pipeline with auto-fix) |

---

## ⚡ Getting Started

### Prerequisites

- Python 3.12+
- Go 1.24+
- Docker (for PostgreSQL)
- Azure CLI (`az login`) — for Azure scanning
- `GEMINI_API_KEY` — Google AI Studio API key (required for AI Copilot & RAG search)

### One-Command Setup

```bash
git clone https://github.com/ankitrout07/Cloud-Reaper.git
cd Cloud-Reaper
python bootstrap.py
```

`bootstrap.py` handles everything automatically:
1. Detects OS (Windows, macOS, Linux) and creates a Python virtual environment
2. Installs all dependencies from `requirements.txt` and `requirements-dev.txt`
3. Builds the Go performance engine binary to `bin/reaper-engine`
4. Scaffolds `.env` file (prompts for credentials including `GEMINI_API_KEY`)
5. Initializes PostgreSQL schema via `init_db()`
6. Launches the dashboard at **http://localhost:5001**

> Full setup guide → **[HOW_TO_RUN.md](HOW_TO_RUN.md)**

### Manual Setup

```bash
# 1. Start PostgreSQL
docker run --name cloud-reaper-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=cloud_reaper \
  -p 5432:5432 -d postgres:15-alpine

# 2. Python environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# 3. Environment variables
cp .env.example .env              # Edit with your credentials

# 4. Build Go engine
cd src/engine-go && go build -o ../../bin/reaper-engine main.go && cd ../..

# 5. Launch dashboard
PYTHONPATH=src python -m reaper.web.app
```

---

## 🐳 Docker Deployment

### Docker Compose (Recommended)

```bash
# Full-stack deployment: app + PostgreSQL
docker compose up -d
```

This launches:
- **`cloud-reaper-db`** — PostgreSQL 15 (Alpine) with persistent volume
- **`cloud-reaper-app`** — Multi-stage build (Go builder → Python 3.12 runtime)

Dashboard available at **http://localhost:5001**

### Standalone Docker Build

```bash
docker build -t cloud-reaper:latest .
docker run -p 5001:5001 \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/cloud_reaper \
  -e AZURE_SUBSCRIPTION_ID=your-sub-id \
  cloud-reaper:latest
```

The Dockerfile uses a multi-stage build:
1. **Stage 1 (`go-builder`)**: Compiles the Go performance engine on `golang:1.24-alpine`
2. **Stage 2 (`python:3.12-slim`)**: Installs Python dependencies, copies source code & Go binary, exposes port 5001

---

## 🧬 Intelligence & ML Models

Cloud-Reaper's Python layer is not a threshold-alert system — it runs real statistical models and a Q-learning RL agent on cloud telemetry.

### 🧟 Zombie Hunter — `ZombieScorer` (`logic.py`)

Heuristic scoring model (0–100) to identify orphaned and idle resources:

| Rule | Condition | Score |
|---|---|---|
| Attachment Status | Storage volume is unattached/orphaned | **+50** |
| IOPS History (7-day) | All data points < 10 IOPS for 7 consecutive days | **+45** |
| IOPS Fallback | Single data point with current IOPS < 5 | **+20** |
| **Zombie Threshold** | Cumulative score **≥ 90** | → flagged + Discord alert |

### 📈 Budget Forecaster — `BudgetForecaster` (`logic.py`)

ARIMA(1,1,1) time-series model for End-of-Month spend projection:

- `AR(1)` — captures day-to-day autoregressive spend correlation  
- `I(1)` — integrates trend differences to achieve stationarity  
- `MA(1)` — smooths erratic batch job billing spikes  
- **Confidence levels**: `low` (<5 days), `medium` (5–14 days), `high` (>14 days)  
- **Fallback**: linear rolling average when history < 5 data points

### 📉 Anomaly Detector — `AnomalyDetector` (`logic.py`)

Seasonal-decomposition anomaly detection to eliminate weekday false positives:

- Applies **additive seasonal decomposition** (period = 7) on ≥ 14 days of spend data
- Analyses the **Residual** component only: `Spend = Trend + Seasonal + Residual`
- Flags anomalies where the residual **Z-score > 3.0**
- Fallback: rolling 7-day window Z-score for datasets < 14 days

### 🤖 Q-Learning Right-Sizing Agent — `RightsizingAgent` (`calculator.py`)

Reinforcement learning agent for VM SKU recommendations:

| Parameter | Value |
|---|---|
| **State space** | (CPU, Mem, IOPS, Network) → 3 tiers each → **81 states** |
| **Tiers** | Low (<30%), Medium (30–70%), High (≥70%) |
| **Actions** | `stay`, `downscale`, `upscale`, `migrate_family` |
| **Learning rate α** | 0.1 |
| **Discount factor γ** | 0.9 |
| **Exploration** | ε-greedy (ε=0.0 during inference for deterministic exploitation) |
| **SLA safety** | High-risk flagged if CPU/Mem >80% during family migration |

### 🔮 Predictive Scaling — `PredictiveScalingEngine` (`workload.py`)

ARIMA(1,1,0) model with a 15-step forecast horizon:

| Directive | Condition |
|---|---|
| `PRE_WARM` | Forecasted peak > 85% — scales up before the spike hits |
| `SCALE_DOWN` | Forecasted peak < 20% AND current load < 30% |
| `STAY` | Load within safe operating boundaries |

### 🎯 Spot Instance Advisor — `SpotEvictionPredictor` (`workload.py`)

GradientBoosting classifier (100 estimators, lr=0.1, depth=3) predicting eviction within 1–4 hours:

- **Features**: `price_volatility`, `demand_index`, `region_capacity`
- **Action**: If eviction probability ≥ 90% → triggers `migrate_gracefully` before forcible reclaim

### 💹 Unit Economics — `BusinessCorrelation` (`economics.py`)

Linear regression (`numpy.polyfit` degree 1) mapping daily infra spend against business KPIs:

- **Slope (dC/dU)** = exact marginal infrastructure cost per additional user
- **Break-even point** = user volume required to cover platform fixed costs
- **ARPU** default = $0.50/user; outputs `EFFICIENT` / `INEFFICIENT` operational signal

---

## 🧠 Cost-Bounded Performance Copilot

The Copilot is a **Bounded Knapsack Optimization Engine** backed by **Gemini 2.5 Flash** (`temperature=0.1`). It translates a free-text workload description and a hard budget cap into a maximum-performance infrastructure blueprint with Terraform HCL.

### API Endpoint

```bash
POST /api/v1/copilot/optimize
```

**Request body:**
```json
{
  "provider": "azure",
  "intent": "high-availability API cluster handling 50k RPM",
  "budget_cap": 1200.00
}
```

**Response schema (Pydantic-validated):**
- `system_architecture_overview` — High-level architecture description
- `infrastructure_components` — Name, SKU, quantity, monthly cost, `perf_factor` justification
- `calculated_total_cost` — Total monthly cost (guaranteed ≤ budget_cap)
- `efficiency_index_score` — Performance-per-dollar score (1–100)
- `production_terraform_hcl` — Ready-to-deploy Terraform with FinOps governance tags

### Features
- **128-entry LRU cache** — composite key (provider + intent + budget); sub-millisecond repeat response
- **Offline fallback** — regex-based rule synthesizer when API key is missing or rate-limited
- **Multi-provider support** — Azure, AWS, GCP with region-specific cost resolution (730 hr/month)
- **Mandatory governance tags** — all generated resources tagged `Env=sandbox`, `Owner=ankit`

> Set `GEMINI_API_KEY` in your `.env` to activate the Copilot.

---

## 🔍 RAG Documentation Search

Cloud-Reaper includes a built-in **Retrieval-Augmented Generation** engine for searching the `docs/` directory with hybrid retrieval.

### 4-Stage Pipeline

1. **Dense Retrieval** — Gemini Embedding for semantic vector similarity
2. **Sparse Retrieval** — Custom BM25 with IDF smoothing for keyword matching
3. **Reciprocal Rank Fusion (RRF)** — Fuses dense + sparse rankings (k=60)
4. **Cross-Encoder Re-Ranking** — Gemini re-scores top candidates for final relevance

### Features
- **Contextual chunk situating** — Each chunk is prefixed with a document-level summary
- **Sliding window enrichment** — Left/right sentence context for richer retrieval
- **Graceful degradation** — Falls back to Jaccard/overlap scoring when Gemini is unavailable
- Drop any Markdown or text file into `docs/` to make it instantly searchable

```bash
POST /api/search
```

---

## 🔐 Cryptographic Audit Trails

Every action performed by Cloud-Reaper's optimization engine is logged with a **cryptographically signed hash chain** ensuring tamper-proof, mathematically verifiable audit trails.

### How It Works

1. An `action_logs` entry is created for each vault access or resource action
2. Row metadata (`resource_id | action_type | details | timestamp | previous_hash`) is concatenated
3. A **SHA-256 hash** is computed → stored as `signature`
4. `previous_hash` links to the preceding row's `signature`, forming a **hash chain**
5. Genesis row uses `previous_hash = "0000...0000"` (64 zeros)

### Verification

To verify any row:
1. Query the row and its predecessor
2. Recompute SHA-256 from row metadata + predecessor's `signature`
3. Compare against the stored `signature`

Any tampered row breaks the chain — all subsequent signatures become invalid.

---

## 🔑 Vault & Secret Management

Cloud-Reaper includes a built-in encrypted vault for managing cloud credentials and secrets with session-level auto-lock.

### Encryption Stack

| Layer | Algorithm | Details |
|---|---|---|
| **Passcode Verification** | PBKDF2-HMAC-SHA256 | **600,000** iterations + 16-byte random salt |
| **Key Derivation** | PBKDF2-HMAC-SHA256 | 100,000 iterations → 32-byte Fernet key |
| **Symmetric Encryption** | Fernet (AES-128-CBC) | URL-safe base64 encoded tokens |
| **Session Security** | Flask session | Key stored in-memory only; auto-purged after `VAULT_UNLOCK_TTL_SEC` (default 3600s) |

### Vault API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/vault/status` | Returns vault configured/unlocked state |
| `POST` | `/api/vault/setup` | Initializes vault with a user passcode |
| `POST` | `/api/vault/unlock` | Validates passcode and unlocks vault |
| `POST` | `/api/vault/lock` | Purges all keys from session |
| `POST` | `/api/vault/reset` | Full wipe of all entries and settings |
| `GET` | `/api/vault/entries` | Lists secret labels (payloads not returned) |
| `POST` | `/api/vault/entries` | Encrypts and saves a new secret |
| `GET` | `/api/vault/entries/<id>` | Decrypts and returns a specific secret |
| `DELETE` | `/api/vault/entries/<id>` | Deletes a secret from the vault |

---

## ☁️ Multi-Cloud Provider Support

| Provider | Go Scanner | Python Collector | Price Client | Features |
|---|---|---|---|---|
| **Azure** | `cloud_scrapers.go` | `providers/azure_collector.py` | `prices/azure.py` | VMs, Disks, Snapshots, NSGs, Monitor Metrics |
| **AWS** | `cloud_scrapers.go` | — (Go scanner) | `prices/aws.py` | EC2, EBS, S3, IAM resource scanning |
| **GCP** | `cloud_scrapers.go` | — | `prices/gcp.py` | Compute Engine, Persistent Disks, GCS, GKE |
| **Kubernetes** | `k8s_scraper.go` | — | — | Pod metrics, node utilization, MostAllocated bin-packing |

All non-Azure collectors implement the unified `CloudProvider` interface:

```go
type CloudProvider interface {
    Authenticate(creds map[string]string) error
    ScanResources() ([]models.Resource, error)
    GetHourlyRate(sku string) (float64, error)
}
```

### Go Engine Scan Modes

```bash
# Default: Full Azure scan (VMs + Orphaned Disks + Snapshots)
./bin/reaper-engine --subscription <AZURE_SUBSCRIPTION_ID>

# List all accessible Azure subscriptions
./bin/reaper-engine --list-subs

# Fetch live Azure Retail Pricing (23 service categories)
./bin/reaper-engine --mode prices

# Regional arbitrage: compare SKU price across regions concurrently
./bin/reaper-engine --mode arbitrage --sku "Standard_D4s_v3" --regions "eastus,westus,westeurope"

# Scan AWS or GCP (credentials from vault or environment)
./bin/reaper-engine --provider aws
./bin/reaper-engine --provider gcp
```

### Provider Authentication

```bash
# Azure — via Azure CLI or Service Principal
az login

# AWS — via environment or cloud_connections vault
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1

# GCP — via Service Account JSON or cloud_connections vault
export GCP_PROJECT_ID=...
export GCP_SERVICE_ACCOUNT_JSON=...
```

Credentials can also be stored in the **encrypted vault** via the Settings UI — the Go engine fetches them dynamically from `cloud_connections`.

---

## 🛑 Shift-Left Cost Simulation (CLI)

Run a PR cost delta report without any live cloud connection — ideal for GitHub Actions pipelines:

```bash
PYTHONPATH=src python -m reaper.cli --pr-simulation [optional-plan-file.json]
```

Outputs a Markdown table of infrastructure changes (CREATE/DESTROY), their cost delta, and governance recommendations — ready to post as a GitHub PR comment.

---

## 🗄️ Database Schema

Cloud-Reaper uses PostgreSQL 15 with **13 managed tables** (auto-initialized via `init_db()`):

| Table | Purpose |
|---|---|
| `resources` | Multi-cloud resource inventory (VMs, disks, snapshots) — JSONB tags |
| `cost_history` | Historical daily cost data (ACTUAL / AMORTIZED) |
| `reap_actions` | Reap command execution log (DEALLOCATE, DELETE) |
| `recommendations` | AI-generated rightsizing and GreenOps recommendations |
| `action_logs` | **Cryptographically signed** SHA-256 hash chain audit trail |
| `business_metrics` | Unit economics data (active users, API requests, CI/CD builds) |
| `region_price_cache` | Lazy-cached multi-cloud SKU pricing per region (Numeric 15,6) |
| `vault_settings` | Single-row vault config (PBKDF2 salt + passcode verifier) |
| `vault_entries` | Fernet-encrypted secret entries (credential, passcode, note) |
| `cloud_connections` | Multi-cloud provider credential manifests (JSONB) |
| `budgets` | Cost envelopes by scope (TAG / PROVIDER / ACCOUNT) |
| `budget_alerts` | Notification thresholds + channel configs per budget |
| `cloud_commitments` | Reserved Instance and Savings Plan contracts (AWS + Azure) |

```bash
# Spin up PostgreSQL
docker run --name cloud-reaper-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=cloud_reaper \
  -p 5432:5432 -d postgres:15-alpine

# Schema auto-initializes via bootstrap.py
```

---

## 📡 API Reference

### Core Scanning

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/scan` | Trigger a full multi-cloud resource scan |
| `POST` | `/api/finops/approve-reap` | Execute a reap action on a target resource |
| `GET` | `/api/activity` | Fetch remediation action log |

### Settings & Cloud Connections

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/settings/subscriptions` | List active cloud subscriptions |
| `POST` | `/api/settings/sync` | Sync Azure credentials to local `.env` |
| `POST` | `/api/settings/update` | Update currency, pricebook, rightsizing profile |
| `POST` | `/api/settings/connect-azure` | Validate and save Azure credentials |
| `POST` | `/api/settings/connect-cloud` | Connect AWS / GCP / Kubernetes credentials |
| `GET` | `/api/context/switch?provider=<type>` | Switch active scanning context |

### Financial Intelligence

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/financial` | Financial intelligence dashboard |
| `GET` | `/api/metrics/compute-waste` | Compute waste index analysis |
| `POST` | `/api/finops/anomalies/triage` | AI-powered anomaly triage and playbook generation |

### AI & Search

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/copilot/optimize` | Cost-Bounded Copilot (Gemini 2.5 Flash) |
| `POST` | `/api/search` | RAG documentation search |
| `GET` | `/build_with_ai` | AI Architect Estimator (interactive BOM builder) |

### Infrastructure & UI

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/pricing` | Regional price intelligence dashboard |
| `GET` | `/integrations` | Multi-channel alerting hub configuration |
| `GET` | `/monitor` | Real-time monitoring dashboard |
| `GET` | `/settings` | Settings & vault management UI |
| `GET` | `/about` | Project info & architecture overview |
| `GET` | `/docs` | In-app RAG-powered documentation browser |

---

## 🧪 CI/CD Pipeline

The GitHub Actions pipeline runs **7 parallel quality gates** on every push/PR to `main`:

```
┌─────────────────────┐
│  auto-lint-format   │  ← Ruff + gofmt + golangci-lint (auto-commits fixes)
└──────────┬──────────┘
     ┌─────▼─────┐    ┌────────────┐
     │test-python │    │  test-go   │    ┌──────────┐
     │ pytest+cov │    │ go test    │    │ security │
     └─────┬─────┘    │ go build   │    │ bandit   │
           │          └─────┬──────┘    │ safety   │
           │                │           └──────────┘
     ┌─────▼────────────────▼─────┐
     │       integration          │  ← DB wiring + engine smoke test
     └────────────┬───────────────┘
     ┌────────────▼───────────────┐
     │       docker-build         │  ← Full Docker image build & verify
     └────────────┬───────────────┘
     ┌────────────▼───────────────┐
     │         summary            │  ← Final CI status report
     └────────────────────────────┘
```

| Job | Depends On | Purpose |
|---|---|---|
| `auto-lint-format` | — | Ruff + Mypy + gofmt + golangci-lint (auto-commits fixes) |
| `test-python` | `auto-lint-format` | Pytest + coverage → Codecov upload |
| `test-go` | `auto-lint-format` | Go tests + binary build → artifact upload |
| `security` | — | Bandit SAST + Safety dependency scan |
| `integration` | `test-python` + `test-go` | PostgreSQL service container + wiring smoke test |
| `docker-build` | `integration` | Full multi-stage Docker image build & verify |
| `summary` | `integration` + `docker-build` | Final CI status report |

---

## 🔧 Development Commands

```bash
make help           # Show all available commands
make install        # Install all dependencies (Python & Go) into venv
make build          # Build Go engine binary → bin/reaper-engine
make test           # Run all tests (Python + Go)
make test-python    # Run Python tests only (pytest + coverage)
make test-go        # Run Go tests only (go test -v ./...)
make lint           # Run all linters (Ruff + Mypy + golangci-lint)
make lint-python    # Run Python linters only
make lint-go        # Run Go linter only
make fmt            # Auto-format all code (Ruff + gofmt + golangci-lint --fix)
make run            # Build and run the application
make clean          # Clean build artifacts and caches
```

---

## ⚙️ Configuration

Create a `.env` file from the provided template:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes** | PostgreSQL connection string |
| `FLASK_PORT` | No | Dashboard port (default: `5001`) |
| `FLASK_HOST` | No | Dashboard bind host (default: `127.0.0.1`) |
| `FLASK_DEBUG` | No | Enable Flask debug mode (`True` / `False`) |
| `AZURE_SUBSCRIPTION_ID` | For Azure | Azure subscription to scan |
| `AZURE_TENANT_ID` | For Azure | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | For Azure | Service Principal app ID |
| `AZURE_CLIENT_SECRET` | For Azure | Service Principal secret |
| `AWS_ACCESS_KEY_ID` | For AWS | AWS IAM access key |
| `AWS_SECRET_ACCESS_KEY` | For AWS | AWS IAM secret key |
| `AWS_REGION` | For AWS | Default AWS region |
| `GCP_PROJECT_ID` | For GCP | Google Cloud project ID |
| `GCP_SERVICE_ACCOUNT_JSON` | For GCP | Service account key JSON (inline or file path) |
| `GEMINI_API_KEY` | For AI features | Google AI Studio key (Copilot, RAG, Triage) |
| `OPENAI_API_KEY` | For AI Architect | OpenAI API key (multi-provider BOM generation) |
| `INFLUXDB_URL` | Optional | InfluxDB endpoint (default: `http://localhost:8086`) |
| `INFLUXDB_TOKEN` | Optional | InfluxDB auth token |
| `INFLUXDB_ORG` | Optional | InfluxDB organisation (default: `ReaperOps`) |
| `INFLUXDB_BUCKET` | Optional | InfluxDB bucket (default: `cloud_burn`) |
| `DISCORD_WEBHOOK_URL` | Optional | Discord alerting webhook |
| `SLACK_WEBHOOK_URL` | Optional | Slack alerting webhook |
| `TEAMS_WEBHOOK_URL` | Optional | Microsoft Teams alerting webhook |

---

## 📜 Changelog

Full history in **[CHANGELOG.md](CHANGELOG.md)**.

**Recent Highlights:**
- **Architecture**: Fully migrated the web layer from synchronous Flask to asynchronous non-blocking **FastAPI + Uvicorn (ASGI)**.
- **Performance (Go)**: Implemented a resident Go HTTP Bridge (`--mode serve`) to eliminate process-fork latency, and integrated a zero-allocation `BatchUpsert` pool (`sync.Pool`) for GC-free PostgreSQL inserts.
- **Performance**: Upgraded `ruff` for faster static analysis; stabilized hybrid Go/Python execution pipelines and reduced memory footprint across resource scrapers
- **Fixes**: Iterative improvements to multi-cloud authentication (Azure/AWS/GCP) and enforced vault log retention policies to prevent unbounded DB growth
- **UI/UX**: Shipped glassmorphism redesign for vault and cloud provider UIs; fine-tuned cyan/slate color palette across the dashboard; added About page, Kubernetes Agent card, and enriched Budget Alerts tab
- **New Models**: Added `Budget`, `BudgetAlert`, and `CloudCommitment` SQLAlchemy tables with unit tests

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run the quality checks (`make lint && make test`)
5. Commit your changes (`git commit -m 'feat: add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

The CI pipeline will automatically lint, format, test, and validate your changes.

---

## 📄 License

This project is licensed under the MIT License.

---

<p align="center">
  Built for Cloud-native FinOps engineering.<br>
  <strong>Cloud-Reaper</strong> — Reap the waste, harvest the savings.
</p>
