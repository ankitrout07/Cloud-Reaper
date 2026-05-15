# ☁️ Cloud-Reaper

[![CI](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitrout07/Cloud-Reaper/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)
![Go](https://img.shields.io/badge/Go-1.24%2B-00ADD8?logo=go)
![License](https://img.shields.io/badge/License-MIT-green)

A high-performance **Hybrid FinOps Intelligence Engine** designed to bridge the gap between cloud finance and engineering action.

Cloud-Reaper uses a **Dual-Core Architecture** (Python + Go) to achieve massive scanning speeds across large-scale Azure environments, providing real-time cost reduction recommendations, regional price arbitrage, and automated governance enforcement.

---

## 🚀 Key Features

### 1. 📊 Inform Phase — Visibility
- **⚡ High-Velocity Scanning:** Custom Go engine with goroutines for sub-second Azure resource auditing.
- **🏷️ Tag Health Score:** Automated audit of critical tags (`Owner`, `Env`) for 100% cost attribution.
- **📈 Anomaly Detection:** Real-time detection of cost spikes via seasonal-aware ARIMA forecasting.
- **🌍 Regional Price Intelligence:** Lazy-cached Azure SKU pricing per region via `RegionPriceCache` (PostgreSQL).

### 2. 📉 Optimize Phase — Waste Reduction
- **🧟 Zombie Hunting:** Identifies orphaned disks, snapshots, and idle compute resources automatically.
- **💎 RI/SP Advisor:** Recommends Reserved Instances based on actual uptime and inventory patterns.
- **❄️ Cold Storage Identifier:** Scans unused storage and suggests Cool/Archive tier migrations.
- **🤖 AI Regional Arbitrage:** Automatically compares SKU pricing across regions and recommends cheaper deployments.

### 3. ⚖️ Operate Phase — Governance
- **🛡️ Policy Guardrails:** Real-time audit against FinOps best practices via Azure Resource Graph.
- **🚨 Budget Kill-Switch:** Automated VM deallocation safeguards for sandbox environments.
- **🔔 Discord Notifications:** Webhook-driven alerts for budget breaches and anomalies.
- **📄 PDF BOM Export:** One-click Bill of Materials export from the Architect Estimator.

---

## 🏗️ Hybrid Architecture

```
                    ┌─────────────────────────────────┐
                    │        Azure Subscription         │
                    └────────────┬────────────────────┘
                                 │  Azure SDK / REST API
               ┌─────────────────▼──────────────────┐
               │   Go Performance Core (engine-go)    │  ← Goroutine-parallel scanner
               │   - network_scraper, k8s_optimizer  │
               │   - auth, db bridge                  │
               └─────────────────┬──────────────────┘
                                 │  PostgreSQL (results)
               ┌─────────────────▼──────────────────┐
               │   Python Intelligence Layer          │  ← FinOps logic & anomaly models
               │   - collectors, engine, services    │
               │   - ARIMA, economics, arbitrage     │
               └─────────────────┬──────────────────┘
                                 │
               ┌─────────────────▼──────────────────┐
               │   Flask/SocketIO Dashboard           │  ← http://localhost:5001
               │   - Real-time WebSocket metrics     │
               │   - Glassmorphism + Cyan Glow UI    │
               └─────────────────────────────────────┘
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
│   │   ├── services/       # Log streamer / notification services
│   │   └── web/            # Flask app, templates, static assets
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
| Frontend | HTML5, Vanilla JS, CSS (Glassmorphism + Cyan Glow) |
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

### One-Command Setup

```bash
git clone https://github.com/ankitrout07/Cloud-Reaper.git
cd Cloud-Reaper
python bootstrap.py
```

`bootstrap.py` handles everything automatically — Go build, venv, dependencies, `.env`, and dashboard launch. Dashboard available at **http://localhost:5001**.

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

## 🗄️ Database

Cloud-Reaper uses PostgreSQL with the following key tables:

| Table | Purpose |
|---|---|
| `resources` | Azure resource inventory |
| `cost_history` | Historical daily cost data |
| `action_logs` | Audit trail for reap actions |
| `business_metrics` | Unit economics data (users, requests) |
| `region_price_cache` | Lazy-cached Azure SKU pricing per region |

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

## 📝 License
MIT License. Built for state-of-the-art Azure FinOps engineering.
