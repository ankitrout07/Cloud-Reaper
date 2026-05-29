# ☁️ Cloud-Reaper

[![CI](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)
![Go](https://img.shields.io/badge/Go-1.24%2B-00ADD8?logo=go)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A high-performance **Hybrid FinOps Intelligence Engine** designed to bridge the gap between cloud finance and engineering action.

Cloud-Reaper uses a **Dual-Core Architecture** (Python + Go) to achieve massive scanning speeds across large-scale multi-cloud environments, providing real-time cost reduction recommendations, regional price arbitrage, automated governance enforcement, cryptographically signed audit trails, and a **Cost-Bounded Performance Copilot** powered by Google Gemini AI.

---

## Table of Contents

- [Key Features](#-key-features)
- [Hybrid Architecture](#-hybrid-architecture)
- [Project Structure](#-project-structure)
- [Tech Stack](#-tech-stack)
- [Getting Started](#-getting-started)
- [Docker Deployment](#-docker-deployment)
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
- [Contributing](#-contributing)

---

## 🚀 Key Features

### 📊 Phase 1 — Inform: Visibility & High-Performance Discovery

| Feature | Description |
|---|---|
| **⚡ High-Velocity Go Scanner** | Custom Go engine with goroutines for sub-second Azure resource auditing across subscriptions |
| **🚀 In-Memory Cache** | Thread-safe global memory caching (`threading.Lock`) with custom TTLs for sub-millisecond dashboard rendering |
| **🏷️ Hierarchical Virtual Tagging** | Builds nested logical metadata tags to map costs to internal business taxonomies without altering cloud tags |
| **🧠 Unified AI/LLM Token Tracking** | Connects to AI providers (OpenAI, Anthropic, etc.) to track generative AI billing alongside infrastructure costs |
| **🏷️ Tag Health Score** | Automated audit of critical tags (`Owner`, `Env`) for 100% cost attribution |
| **📈 ARIMA Anomaly Detection** | Real-time detection of cost spikes via seasonal-aware ARIMA time-series forecasting |
| **🌍 Regional Price Intelligence** | Lazy-cached Azure/AWS/GCP SKU pricing per region via `RegionPriceCache` (PostgreSQL) |

### 📉 Phase 2 — Optimize: Waste & Carbon Reduction

| Feature | Description |
|---|---|
| **📦 Cluster Bin-Packing** | Evaluates Kubernetes pod requirements in real-time, executes live migrations to maximize node utilization |
| **💤 Zero-Downtime Hibernation** | Scales non-production clusters to zero during off-hours, instant spin-up on developer request |
| **🌱 GreenOps Carbon Index** | Live Regional Grid Carbon Intensity estimation (gCO2eq/kWh) with green migration recommendations |
| **🧟 Zombie Hunting** | Identifies orphaned disks, snapshots, and idle compute resources automatically |
| **💎 RI/SP Advisor** | Recommends Reserved Instances based on actual uptime and inventory patterns |
| **❄️ Cold Storage Identifier** | Scans unused storage and suggests cost-efficient Cool/Archive tier migrations |
| **🤖 AI Regional Arbitrage** | Multi-cloud real-time pricing clients with region-to-region arbitrage estimation |
| **🧠 Cost-Bounded Copilot** | Bounded Knapsack Optimizer backed by **Gemini 2.5 Flash** with 128-entry LRU cache |

### ⚖️ Phase 3 — Operate: Governance & Security

| Feature | Description |
|---|---|
| **🛑 Shift-Left Cost Simulation** | Dry-run estimations in GitHub Actions/Terraform before code is merged |
| **🛡️ Policy Guardrails** | Real-time audit against FinOps best practices via Azure Resource Graph |
| **🚨 Budget Kill-Switch** | Automated VM deallocation for sandbox environments |
| **🔔 Multi-Channel Alerting** | Webhook-driven alerts via Discord, Slack, and Microsoft Teams |
| **📄 PDF BOM Export** | One-click Bill of Materials export from the Architect Estimator (WeasyPrint) |
| **💼 Commitment Tracking** | Centralized tracking of Savings Plans and Reserved Instances across AWS and Azure |
| **☸️ Kubernetes Agent** | Connection monitoring for container cost allocation and cluster bin-packing |
| **🔐 Cryptographic Audit Trails** | SHA-256 chained hash ledger for tamper-proof action log verification |
| **🔑 Encrypted Vault** | PBKDF2-derived Fernet (AES-128-CBC) encryption for credential management |

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
                          │   ├── azure_scraper    (ARM + Monitor)  │
                          │   ├── aws_scraper      (EC2 + S3)      │
                          │   ├── gcp_scraper      (Compute + GKE) │
                          │   ├── k8s_scraper      (Metrics API)   │
                          │   ├── k8s_optimizer    (Bin-Packing)   │
                          │   ├── network_scraper  (NSG Audit)     │
                          │   ├── price_client     (Retail API)    │
                          │   ├── auth             (Graph API)     │
                          │   └── db bridge        (pgx/v5)        │
                          └────────────────────┬────────────────────┘
                                               │  PostgreSQL 15
                          ┌────────────────────▼────────────────────┐
                          │   Python Intelligence Layer             │
                          │   ├── collectors/  Azure, AWS, GCP      │
                          │   ├── engine/      Models, ARIMA, Econ  │
                          │   ├── rag/         BM25 + Gemini RRF    │
                          │   ├── services/    Log Streamer, Pusher │
                          │   └── web/         Flask + SocketIO     │
                          └────────────────────┬────────────────────┘
                                               │
                          ┌────────────────────▼────────────────────┐
                          │   Flask/SocketIO Dashboard              │
                          │   ├── Real-time WebSocket metrics       │
                          │   ├── Professional Dark Theme UI        │
                          │   ├── Vault & Credential Management     │
                          │   └── http://localhost:5001             │
                          └─────────────────────────────────────────┘
```

### Data Flow

1. **Go Scanner** concurrently scrapes multi-cloud APIs using goroutines with rate-limited ARM calls
2. Resource data is normalized and batch-upserted into PostgreSQL via `pgx/v5`
3. **Python Intelligence Layer** queries the DB, runs ARIMA anomaly detection, cost calculations, and economics models
4. **Flask Dashboard** renders real-time metrics via WebSocket (SocketIO) with in-memory cache acceleration
5. Every credential vault read and resource action is logged into a **cryptographically signed hash chain** for tamper detection

---

## 📂 Project Structure

```text
Cloud-Reaper/
├── bin/                        # Compiled Go binaries (reaper-engine)
├── bootstrap.py                # Universal cross-platform setup script
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
├── src/
│   ├── reaper/                 # Python Intelligence & Web Layer
│   │   ├── collectors/         # Multi-cloud scrapers & price clients
│   │   │   ├── azure_collector.py    # Core Azure resource collector (52KB)
│   │   │   ├── aws_collector.py      # AWS EC2/S3 resource collector
│   │   │   ├── azure_prices.py       # Azure Retail Pricing API client
│   │   │   ├── aws_prices.py         # AWS Pricing API client
│   │   │   ├── gcp_prices.py         # GCP Pricing API client
│   │   │   ├── config_manager.py     # Centralized configuration management
│   │   │   ├── auth_check.py         # Azure credential validation
│   │   │   └── prometheus_finops.py  # Prometheus metric bridge
│   │   ├── engine/             # FinOps models, scheduler, notifier, economics
│   │   │   ├── models.py            # SQLAlchemy ORM (14 tables)
│   │   │   ├── architect.py          # Infrastructure Architect Estimator
│   │   │   ├── calculator.py         # Cost calculation engine
│   │   │   ├── economics.py          # Unit economics analysis
│   │   │   ├── logic.py              # Core FinOps business logic
│   │   │   ├── workload.py           # Workload analysis & profiling
│   │   │   ├── copilot_engine.py     # KnapsackCopilotEngine (Gemini GenAI)
│   │   │   ├── copilot_schemas.py    # Pydantic schemas for structured LLM output
│   │   │   ├── metrics_analyzer.py   # Telemetry metrics analysis
│   │   │   ├── scheduler.py          # Background job scheduler
│   │   │   ├── notifier.py           # Multi-channel notification dispatcher
│   │   │   └── schema.py             # Data validation schemas
│   │   ├── rag/                # Retrieval-Augmented Generation engine
│   │   │   └── engine.py            # BM25 + Gemini Embedding hybrid search
│   │   ├── services/           # Background services
│   │   │   ├── log_streamer.py       # WebSocket log streaming service
│   │   │   └── pusher.py             # Push notification service
│   │   └── web/                # Flask app, templates, static assets
│   │       ├── app.py                # Main Flask application (58KB)
│   │       ├── copilot_routes.py     # Blueprint: /api/v1/copilot/optimize
│   │       ├── metrics_routes.py     # Blueprint: /api/metrics/*
│   │       ├── search_routes.py      # Blueprint: /api/search
│   │       ├── vault_crypto.py       # PBKDF2 + Fernet encryption helpers
│   │       ├── templates/            # Jinja2 templates (12 pages)
│   │       └── static/              # CSS (Professional Dark Theme), JS, assets
│   └── engine-go/              # Go High-Velocity Performance Core
│       ├── main.go                   # Entry point, scanner orchestration (541 lines)
│       ├── collectors/               # Multi-cloud resource scrapers
│       │   ├── azure_scraper.go      # Azure ARM resource scanner
│       │   ├── aws_scraper.go        # AWS EC2/S3 scanner
│       │   ├── gcp_scraper.go        # GCP Compute/GKE scanner
│       │   ├── k8s_scraper.go        # Kubernetes Metrics API scanner
│       │   ├── k8s_optimizer.go      # MostAllocated bin-packing optimizer
│       │   ├── network_scraper.go    # NSG security audit scanner
│       │   ├── price_client.go       # Azure Retail Pricing API client
│       │   ├── auth.go               # Microsoft Graph user identity
│       │   └── provider.go           # Multi-cloud provider abstraction
│       └── db/
│           └── db.go                 # PostgreSQL bridge (pgx/v5) + crypto audit
├── tests/
│   ├── unit/                   # Python unit tests
│   ├── integration/            # Integration tests (requires live DB)
│   └── experimental/           # Exploratory tests & scratch scripts
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
| **Web Framework** | Flask + Flask-SocketIO (gevent WebSocket transport) |
| **AI Copilot** | Google GenAI (`google-genai`) · Gemini 2.5 Flash · Bounded Knapsack Optimizer |
| **RAG Search** | BM25 sparse retrieval + Gemini Embedding dense retrieval + RRF fusion |
| **Frontend** | HTML5, Vanilla JS, CSS (Professional Dark Theme, Adaptive Light/Dark Mode) |
| **Charting** | Chart.js (real-time WebSocket-driven telemetry graphs) |
| **PDF Export** | WeasyPrint |
| **Encryption** | PBKDF2-HMAC-SHA256 (480K iterations) + Fernet (AES-128-CBC) |
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
1. Creates Python virtual environment and installs dependencies
2. Builds the Go performance engine binary
3. Scaffolds `.env` file (including `GEMINI_API_KEY` placeholder)
4. Initializes PostgreSQL schema via `init_db()`
5. Launches the dashboard at **http://localhost:5001**

> Full setup guide → **[HOW_TO_RUN.md](HOW_TO_RUN.md)**

### Manual Setup

```bash
# 1. Start PostgreSQL
docker run --name cloud-reaper-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=cloud_reaper -p 5432:5432 -d postgres:15-alpine

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

## 🧠 Cost-Bounded Performance Copilot

The Copilot is a **Bounded Knapsack Optimization Engine** wrapped in an LLM heuristic proxy. It translates a free-text workload description and a hard budget cap into a maximum-performance, production-tagged infrastructure blueprint with Terraform HCL.

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

**Response includes:**
- `system_architecture_overview` — High-level architecture description
- `infrastructure_components` — Name, SKU, quantity, monthly cost, performance justification
- `calculated_total_cost` — Total monthly cost (guaranteed ≤ budget_cap)
- `efficiency_index_score` — Performance-to-cost ratio score
- `production_terraform_hcl` — Ready-to-deploy Terraform code

### Features
- **128-entry LRU cache** for sub-millisecond repeat query resolution
- **Pydantic structured output** schemas for type-safe LLM responses
- **Multi-provider support** (Azure, AWS, GCP)

> Set `GEMINI_API_KEY` in your `.env` to activate the Copilot.

---

## 🔍 RAG Documentation Search

Cloud-Reaper includes a built-in **Retrieval-Augmented Generation** engine for searching project documentation with state-of-the-art hybrid retrieval.

### Architecture

The RAG pipeline implements a 4-stage search strategy:

1. **Dense Retrieval** — Gemini Embedding (`gemini-embedding-2`) for semantic vector similarity
2. **Sparse Retrieval** — Custom BM25 implementation with IDF smoothing for keyword matching
3. **Reciprocal Rank Fusion (RRF)** — Combines dense and sparse rankings (k=60)
4. **Cross-Encoder Re-Ranking** — Gemini 2.5 Flash re-scores top candidates for final relevance ordering

### Features
- **Claude-style contextual chunk situating** — Each sentence chunk is prefixed with document-level summary context
- **Sliding window enrichment** — Left/right sentence context for richer retrieval results
- **Graceful degradation** — Falls back to Jaccard/overlap scoring when Gemini is unavailable

### API Endpoint

```bash
POST /api/search
```

---

## 🔐 Cryptographic Audit Trails

Every action performed by Cloud-Reaper's optimization engine is logged with a **cryptographically signed hash chain**, ensuring tamper-proof audit trails that security teams can mathematically verify.

### How It Works

1. When the Go scraper reads a credential from the vault, an `action_logs` entry is created
2. The log entry's metadata (`resource_id | action_type | details | timestamp | previous_hash`) is concatenated
3. A **SHA-256 hash** is computed to produce the `signature`
4. The `previous_hash` field points to the preceding row's `signature`, forming a **hash chain**
5. If the table is empty, a genesis hash (`0000...0000`) is used as the initial `previous_hash`

### Verification

Any row can be verified by:
1. Querying the row and its predecessor
2. Recomputing the SHA-256 hash from the row's metadata + predecessor's signature
3. Comparing the computed hash against the stored `signature`

If any row has been tampered with, the chain breaks and all subsequent signatures become invalid.

---

## 🔑 Vault & Secret Management

Cloud-Reaper includes a built-in encrypted vault for managing cloud credentials and secrets.

### Encryption Stack

| Layer | Algorithm | Details |
|---|---|---|
| **Key Derivation** | PBKDF2-HMAC-SHA256 | 480,000 iterations with random salt |
| **Symmetric Encryption** | Fernet (AES-128-CBC) | URL-safe base64 encoded tokens |
| **Passcode Verification** | SHA-256 | Salt-prepended hash comparison |

### Vault Features
- **Passcode-protected access** — Vault is locked by default; requires passcode to decrypt entries
- **Encrypted payload storage** — Credentials stored as Fernet-encrypted JSON blobs
- **Multi-type entries** — Supports `credential`, `passcode`, and `note` entry types
- **Cloud Connections** — Dedicated `cloud_connections` table for multi-cloud provider credential manifests (Azure, AWS, GCP, K8s)

---

## ☁️ Multi-Cloud Provider Support

Cloud-Reaper supports scanning and cost analysis across multiple cloud providers:

| Provider | Go Scanner | Python Collector | Price Client | Features |
|---|---|---|---|---|
| **Azure** | `azure_scraper.go` | `azure_collector.py` | `azure_prices.py` | VMs, Disks, Snapshots, NSGs, Monitor Metrics |
| **AWS** | `aws_scraper.go` | `aws_collector.py` | `aws_prices.py` | EC2, S3, IAM resource scanning |
| **GCP** | `gcp_scraper.go` | — | `gcp_prices.py` | Compute Engine, GKE cluster scanning |
| **Kubernetes** | `k8s_scraper.go` | — | — | Pod metrics, node utilization, bin-packing |

### Provider Authentication

```bash
# Azure (Default — via Azure CLI or Service Principal)
az login

# AWS (via environment variables or cloud_connections vault)
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1

# GCP (via Service Account JSON or cloud_connections vault)
export GCP_PROJECT_ID=...
export GCP_SERVICE_ACCOUNT_JSON=...
```

Credentials can also be stored in the **encrypted vault** via the Settings UI, and the Go engine will fetch them dynamically from the `cloud_connections` database table.

---

## 🗄️ Database Schema

Cloud-Reaper uses PostgreSQL 15 with 14 managed tables:

| Table | Purpose |
|---|---|
| `resources` | Multi-cloud resource inventory (VMs, disks, snapshots) |
| `cost_history` | Historical daily cost data (ACTUAL / AMORTIZED) |
| `reap_actions` | Reap command execution log (DEALLOCATE, DELETE) |
| `recommendations` | AI-generated rightsizing and GreenOps recommendations |
| `action_logs` | **Cryptographically signed** audit trail with hash chain |
| `business_metrics` | Unit economics data (active users, API requests, CI/CD builds) |
| `region_price_cache` | Lazy-cached multi-cloud SKU pricing per region |
| `vault_settings` | Vault configuration (PBKDF2 salt + passcode verifier) |
| `vault_entries` | Fernet-encrypted secret entries |
| `cloud_connections` | Multi-cloud provider credential manifests (JSON) |
| `budgets` | Static and seasonally adjusted cost envelopes |
| `budget_alerts` | Notification dispatch configurations for budgets |
| `cloud_commitments` | Multi-cloud Reserved Instance and Savings Plan contracts |

### Quick Start

```bash
# Spin up PostgreSQL
docker run --name cloud-reaper-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=cloud_reaper \
  -p 5432:5432 -d postgres:15-alpine

# Schema is auto-initialized by bootstrap.py via init_db()
```

---

## 📡 API Reference

### Core Scanning

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/scan` | Trigger a full multi-cloud resource scan |
| `POST` | `/api/finops/approve-reap` | Execute a reap action on a target resource |
| `GET` | `/api/activity` | Fetch remediation action log |

### Financial Intelligence

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/financial` | Financial intelligence dashboard |
| `GET` | `/api/metrics/compute-waste` | Compute waste index analysis |

### AI & Search

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/copilot/optimize` | Cost-Bounded Performance Copilot |
| `POST` | `/api/search` | RAG documentation search |

### Settings & Vault

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/settings/subscriptions` | List active cloud subscriptions |
| `GET` | `/settings` | Settings & vault management UI |

### Infrastructure

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/pricing` | Regional price intelligence dashboard |
| `GET` | `/integrations` | Multi-channel alerting hub configuration |
| `GET` | `/monitor` | Real-time monitoring dashboard |

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
make install        # Install all dependencies (Python & Go)
make build          # Build Go engine binary
make test           # Run all tests (Python + Go)
make test-python    # Run Python tests only (pytest)
make test-go        # Run Go tests only
make lint           # Run all linters (Ruff + Mypy + golangci-lint)
make lint-python    # Run Python linters only
make lint-go        # Run Go linter only
make fmt            # Auto-format all code (Ruff + gofmt)
make run            # Build and run the application
make clean          # Clean build artifacts and caches
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file from the provided template:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `AZURE_SUBSCRIPTION_ID` | For Azure | Azure subscription to scan |
| `AZURE_TENANT_ID` | For Azure | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | For Azure | Service Principal app ID |
| `AZURE_CLIENT_SECRET` | For Azure | Service Principal secret |
| `AWS_ACCESS_KEY_ID` | For AWS | AWS IAM access key |
| `AWS_SECRET_ACCESS_KEY` | For AWS | AWS IAM secret key |
| `AWS_REGION` | For AWS | Default AWS region |
| `GCP_PROJECT_ID` | For GCP | Google Cloud project ID |
| `GCP_SERVICE_ACCOUNT_JSON` | For GCP | Service account key JSON |
| `GEMINI_API_KEY` | For AI features | Google AI Studio API key |
| `DISCORD_WEBHOOK_URL` | Optional | Discord alerting webhook |
| `SLACK_WEBHOOK_URL` | Optional | Slack alerting webhook |
| `TEAMS_WEBHOOK_URL` | Optional | Microsoft Teams alerting webhook |

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
