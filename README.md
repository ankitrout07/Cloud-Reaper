# ☁️ Cloud-Reaper

[![CI](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)
![Go](https://img.shields.io/badge/Go-1.24%2B-00ADD8?logo=go)
![License](https://img.shields.io/badge/License-MIT-green)

A high-performance **Hybrid FinOps Intelligence Engine** designed to bridge the gap between cloud finance and engineering action.

Cloud-Reaper uses a **Dual-Core Architecture** (Python + Go) to achieve massive scanning speeds across large-scale multi-cloud environments, providing real-time cost reduction recommendations, regional price arbitrage, automated governance enforcement, and a **Cost-Bounded Performance Copilot** powered by Google Gemini AI.

---

## 🚀 Key Features

### 1. 📊 Inform Phase — Visibility & High Performance
- **⚡ High-Velocity Scanning:** Custom Go engine with goroutines for sub-second Azure resource auditing.
- **🚀 High-Performance In-Memory Cache:** Thread-safe global memory caching (`threading.Lock`) with custom TTLs for Go scans and Azure VM inventories, delivering sub-millisecond dashboard page rendering on refresh.
- **🏷️ Hierarchical Virtual Tagging:** Programmatically builds nested, logical metadata tags to map costs to internal business taxonomies without altering physical cloud tags.
- **🧠 Unified AI/LLM Token Tracking:** Connects to external AI providers (OpenAI, Anthropic, etc.) to track generative AI API billing metrics alongside standard infrastructure costs.
- **🏷️ Tag Health Score:** Automated audit of critical tags (`Owner`, `Env`) for 100% cost attribution.
- **📈 Anomaly Detection:** Real-time detection of cost spikes via seasonal-aware ARIMA forecasting.
- **🌍 Regional Price Intelligence:** Lazy-cached Azure/AWS/GCP SKU pricing per region via `RegionPriceCache` (PostgreSQL).

### 2. 📉 Optimize & GreenOps Phase — Waste & Carbon Reduction
- **📦 Continuous Cluster Bin-Packing:** Evaluates Kubernetes pod requirements in real-time, executing live container migrations to maximize node utilization and terminate empty VMs automatically.
- **💤 Deep Zero-Downtime Cluster Hibernation:** Scales non-production clusters down to zero during non-working hours, instantly spinning them back up upon developer request.
- **🌱 Dynamic GreenOps Carbon Index:** Live estimation of Regional Grid Carbon Intensity (gCO2eq/kWh) for virtual machine fleets, generating geographic placement recommendations for green migration.
- **🧟 Zombie Hunting:** Identifies orphaned disks, snapshots, and idle compute resources automatically.
- **💎 RI/SP Advisor:** Recommends Reserved Instances based on actual uptime and inventory patterns.
- **❄️ Cold Storage Identifier:** Scans unused storage dynamically and suggests cost-efficient Cool/Archive tier migrations.
- **🤖 AI Regional Arbitrage:** Standard-compliant multi-cloud (AWS, GCP, Azure) real-time pricing clients offering region-to-region arbitrage estimation.
- **🧠 Cost-Bounded Performance Copilot:** A Bounded Knapsack Optimization Engine backed by **Gemini 2.5 Flash** that generates maximum-performance infrastructure stacks (with production Terraform HCL) strictly bounded by a user-defined monthly budget. Features in-memory FIFO caching (128-entry LRU) for sub-millisecond repeat query resolution.

### 3. ⚖️ Operate Phase — Governance
- **🛑 Shift-Left PR Cost Simulation:** Integrates with code control planes (GitHub Actions/Terraform) to run dry-run estimations, preventing expensive infrastructure mistakes before code is merged.
- **🛡️ Policy Guardrails:** Real-time audit against FinOps best practices via Azure Resource Graph.
- **🚨 Budget Kill-Switch:** Automated VM deallocation safeguards for sandbox environments.
- **🔔 Multi-Channel Alerting Hub:** Webhook-driven alerts via Discord, Slack, and Microsoft Teams for budget breaches, thresholds, and scheduled reports.
- **📄 PDF BOM Export:** One-click Bill of Materials export from the Architect Estimator.
- **💼 Cloud Commitment Tracking:** Centralized tracking of Multi-Cloud Savings Plans and Reserved Instances across AWS and Azure.
- **☸️ Kubernetes Agent Integration:** Seamless connection monitoring for container cost allocation and cluster bin-packing.

---

## 🏗️ Hybrid Architecture

```
                    ┌─────────────────────────────────┐
                    │        Azure Subscription       │
                    └────────────┬────────────────────┘
                                 │  Azure SDK / REST API
               ┌─────────────────▼──────────────────┐
               │   Go Performance Core (engine-go)  │  ← Goroutine-parallel scanner
               │   - network_scraper, k8s_optimizer │
               │   - auth, db bridge                │
               └─────────────────┬──────────────────┘
                                 │  PostgreSQL (results)
               ┌─────────────────▼──────────────────┐
               │   Python Intelligence Layer        │  ← FinOps logic & anomaly models
               │   - collectors, engine, services   │
               │   - ARIMA, economics, arbitrage    │
               └─────────────────┬──────────────────┘
                                 │
               ┌─────────────────▼──────────────────┐
               │   Flask/SocketIO Dashboard         │  ← http://localhost:5001
               │   - Real-time WebSocket metrics    │
               │   - Glassmorphism + Cyan Glow UI   │
               └────────────────────────────────────┘
```

---

## 📂 Project Structure

```text
Cloud-Reaper/
├── bin/                    # Compiled Go binaries (reaper-engine)
├── bootstrap.py            # Universal cross-platform setup script
├── main.py                 # CLI entry point
├── Makefile                # Developer shortcuts (install, build, test, lint)
├── pyproject.toml          # Ruff, Mypy, Pytest configuration
├── requirements.txt        # Runtime dependencies (grouped by category)
├── requirements-dev.txt    # Dev/CI dependencies (Ruff, Mypy, Pytest, Bandit)
├── scripts/
│   └── reap.sh             # Linux/macOS shell entrypoint
├── src/
│   ├── reaper/             # Python Intelligence & Web Layer
│   │   ├── collectors/     # Azure scrapers, auth, config manager, price client
│   │   ├── engine/         # FinOps models, scheduler, notifier, economics
│   │   │   ├── copilot_engine.py   # KnapsackCopilotEngine (Gemini GenAI)
│   │   │   └── copilot_schemas.py  # Pydantic schemas for structured LLM output
│   │   ├── services/       # Log streamer / notification services
│   │   └── web/            # Flask app, templates, static assets
│   │       ├── copilot_routes.py   # Blueprint: /api/v1/copilot/optimize
│   │       ├── templates/          # Jinja templates (index, about, financial, integrations)
│   │       └── static/             # Light/Dark mode CSS and High-fidelity UI assets
│   └── engine-go/          # Go High-Velocity Performance Core
│       ├── collectors/     # network_scraper, k8s_optimizer, auth
│       ├── db/             # PostgreSQL bridge
│       └── main.go
└── tests/
    ├── unit/               # Python unit tests
    ├── integration/        # Integration tests (requires live DB)
    └── experimental/       # Scratch scripts & exploratory tests
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Language (Python) | Python 3.12+ |
| Language (Go) | Go 1.24+ |
| Database | PostgreSQL 15 (SQLAlchemy 2.0) |
| Web Framework | Flask + Flask-SocketIO (gevent) |
| AI Copilot | Google GenAI (`google-genai`) · Gemini 2.5 Flash · Bounded Knapsack Optimizer |
| Frontend | HTML5, Vanilla JS, CSS (Glassmorphism + Cyan Glow, Adaptive Light/Dark Mode) |
| PDF Export | WeasyPrint |
| Python Quality | Ruff · Mypy · Pytest · Bandit · Safety |
| Go Quality | Golangci-lint |
| CI/CD | GitHub Actions |

---

## ⚡ Getting Started

### Prerequisites
- Python 3.12+
- Go 1.24+
- Docker (for PostgreSQL)
- Azure CLI (`az login`)
- `GEMINI_API_KEY` — Google AI Studio API key (required for the AI Copilot)

### One-Command Setup

```bash
git clone https://github.com/ankitrout07/Cloud-Reaper.git
cd Cloud-Reaper
python bootstrap.py
```

`bootstrap.py` handles everything automatically — Go build, venv, dependencies, `.env` (including `GEMINI_API_KEY` scaffolding), and dashboard launch. Dashboard available at **http://localhost:5001**. Explore the System Overview, Architecture, and About pages directly from the dashboard!

> Full setup guide → **[HOW_TO_RUN.md](HOW_TO_RUN.md)**
> Portability & Docker guide → **[PORTABILITY.md](PORTABILITY.md)**

### Manual Setup (if needed)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env              # Edit with your Azure credentials
PYTHONPATH=src python -m reaper.web.app
```

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

**Response includes:** `system_architecture_overview`, `infrastructure_components` (name, SKU, quantity, monthly cost, perf justification), `calculated_total_cost`, `efficiency_index_score`, and `production_terraform_hcl`.

> Set `GEMINI_API_KEY` in your `.env` to activate the Copilot.

---

## 🗄️ Database

Cloud-Reaper uses PostgreSQL with the following key tables:

| Table | Purpose |
|---|---|
| `resources` | Azure resource inventory |
| `cost_history` | Historical daily cost data |
| `action_logs` | Audit trail for reap actions |
| `business_metrics` | Unit economics data (users, requests) |
| `region_price_cache` | Lazy-cached Azure SKU pricing per region |
| `vault_entries` | Encrypted secret entries (Fernet AES-128) |
| `cloud_connections` | Multi-cloud provider credential manifests |
| `budgets` | Static and seasonally adjusted cost envelopes |
| `budget_alerts` | Notification dispatch configurations for budgets |
| `cloud_commitments` | Multi-cloud reserved instance and savings plan contracts |

Run `docker run --name cloud-reaper-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres` to spin up a local DB, then `bootstrap.py` will run `init_db()` automatically.

---

## 🧪 CI Pipeline

The GitHub Actions pipeline runs **parallel quality gates** on every push/PR to `main`:

| Job | Depends On | Purpose |
|---|---|---|
| `lint-python` | — | Ruff + Mypy |
| `lint-go` | — | Golangci-lint |
| `security` | — | Bandit + Safety scan |
| `test-python` | `lint-python` | Pytest + coverage |
| `test-go` | `lint-go` | Go tests + binary build |
| `integration` | `test-python` + `test-go` | DB wiring + engine smoke test |

---
Built for Cloud-native FinOps engineering.

