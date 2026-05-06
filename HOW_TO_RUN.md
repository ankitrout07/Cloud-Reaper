# 📖 How to Run Cloud-Reaper

A comprehensive, workstation-specific guide for setting up and running Cloud-Reaper on **Linux (Ubuntu)**, **macOS**, and **Windows**.

---

## 🛠️ Prerequisites

Install the following before starting:

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) |
| Go | 1.24+ | [golang.org/dl](https://golang.org/dl/) |
| Docker | Latest | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Azure CLI | Latest | `brew install azure-cli` / `winget install Microsoft.AzureCLI` |
| Git | Latest | [git-scm.com](https://git-scm.com/) |

Authenticate with Azure before running:
```bash
az login
```

---

## ⚡ Method 1 — Universal Bootstrap (Recommended)

Works on **macOS, Linux, and Windows** with a single command.

```bash
# Clone the repository
git clone https://github.com/ankitrout07/Cloud-Reaper.git
cd Cloud-Reaper

# Run the universal bootstrap script
python bootstrap.py
```

### What `bootstrap.py` does automatically:
1. ✅ Verifies Go and Docker are installed
2. ✅ Starts a PostgreSQL Docker container (`cloud-reaper-db`)
3. ✅ Builds the Go performance engine (`src/engine-go/reaper-engine`)
4. ✅ Creates a Python virtual environment (`./venv`)
5. ✅ Installs all Python dependencies (`requirements.txt` + `requirements-dev.txt`)
6. ✅ Generates a default `.env` file if one doesn't exist
7. ✅ Launches the dashboard at **http://localhost:5001**

> **macOS note:** Port 5001 is used by default to avoid AirPlay Receiver conflicts on port 5000.

---

## 🔧 Method 2 — Makefile (For Developers)

The `Makefile` provides clean, composable commands for the full development workflow.

```bash
# See all available targets
make help

# Install all Python and Go dependencies
make install

# Build the Go engine binary
make build

# Run all linters (Ruff + Mypy + Golangci-lint)
make lint

# Run all tests (Python + Go)
make test

# Start the application (builds Go engine first, then runs reap.sh)
make run

# Clean all build artifacts and caches
make clean
```

---

## 🛠️ Method 3 — Manual Step-by-Step

For full control or debugging.

### Step 1 — Clone & Enter Directory
```bash
git clone https://github.com/ankitrout07/Cloud-Reaper.git
cd Cloud-Reaper
```

### Step 2 — Set Up Python Environment
```bash
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# .\venv\Scripts\activate         # Windows (PowerShell)

pip install -r requirements.txt -r requirements-dev.txt
```

### Step 3 — Build the Go Engine
```bash
cd src/engine-go
go build -o reaper-engine main.go
cd ../..
```

### Step 4 — Start PostgreSQL
```bash
docker run --name cloud-reaper-db \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 -d postgres
```

### Step 5 — Configure Environment

Create a `.env` file at the project root:

```env
# App
APP_ENV=development
FLASK_PORT=5001
FLASK_DEBUG=True

# Azure (required for live scans)
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres

# Notifications (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Step 6 — Launch the Dashboard
```bash
export PYTHONPATH=$(pwd)/src
python -m reaper.web.app
```

Dashboard: **http://localhost:5001**

### Step 7 — (Optional) CLI Scan Only
```bash
export PYTHONPATH=$(pwd)/src
python main.py
```

---

## 🧪 Quality Gates

Run the full quality suite locally to match the CI pipeline:

### Python Linting (Ruff)
```bash
ruff check src/reaper bootstrap.py main.py
```

### Type Checking (Mypy)
```bash
mypy src/reaper --ignore-missing-imports
```

### Python Tests
```bash
pytest
```

### Go Linting
```bash
cd src/engine-go
golangci-lint run ./...
```

### Go Tests
```bash
cd src/engine-go
go test -v ./...
```

### Security Scan (Bandit + Safety)
```bash
bandit -r src/reaper
safety check --file requirements.txt
```

---

## 📋 Environment Variables Reference

| Variable | Required | Description | Default |
|---|---|---|---|
| `AZURE_SUBSCRIPTION_ID` | ✅ | Target Azure Subscription | — |
| `AZURE_TENANT_ID` | ✅ | Azure AD Tenant | — |
| `AZURE_CLIENT_ID` | ✅ | Service Principal App ID | — |
| `AZURE_CLIENT_SECRET` | ✅ | Service Principal Secret | — |
| `DATABASE_URL` | ✅ | PostgreSQL connection string | — |
| `FLASK_PORT` | ❌ | Dashboard port | `5001` |
| `FLASK_HOST` | ❌ | Dashboard bind address | `127.0.0.1` |
| `FLASK_DEBUG` | ❌ | Enable debug mode | `True` |
| `DISCORD_WEBHOOK_URL` | ❌ | Budget alert notifications | — |

---

## 🆘 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: reaper` | `PYTHONPATH` not set | Run with `python -m reaper.web.app` or set `export PYTHONPATH=$(pwd)/src` |
| `Address already in use :5001` | Another process on 5001 | `lsof -i :5001` and kill the process, or set `FLASK_PORT=5002` in `.env` |
| `FATAL: role "postgres" does not exist` | DB container not running | `docker start cloud-reaper-db` or re-run `bootstrap.py` |
| `go: command not found` | Go not in PATH | Add Go to PATH: `export PATH=$PATH:/usr/local/go/bin` |
| `reaper-engine: permission denied` | Binary not executable | `chmod +x src/engine-go/reaper-engine` |
| `az: command not found` | Azure CLI not installed | Follow [Azure CLI install guide](https://learn.microsoft.com/cli/azure/install-azure-cli) |
| `403 Forbidden` on Azure calls | Expired token / wrong subscription | Re-run `az login && az account set --subscription <id>` |

---

## 🚀 Next Steps After Setup

1. Open the dashboard at **http://localhost:5001**
2. Go to **Settings → Azure Subscription** and paste your Subscription ID
3. Run a **Global Scan** to identify optimization opportunities
4. Review **Zombie Resources** and take recommended cleanup actions
5. Set up **Budget Guardrails** to prevent future cost overruns
6. Configure a **Discord Webhook** for real-time budget alerts
