# 📖 How to Run Cloud-Reaper

A comprehensive guide to set up and run Cloud-Reaper for hybrid cloud cost optimization.

---

## 🛠 Prerequisites

Before you start, ensure you have the following installed:
- **Python 3.12+**
- **Go 1.24+** (for the high-velocity engine)
- **Docker** (for PostgreSQL)
- **Azure CLI** (`az login` to authenticate)

---

## ⚡ Quick Start (Cross-Platform)

The easiest way to get started on **macOS, Windows, or Linux** is using the universal bootstrap script.

```bash
# Run the universal bootstrap script
python bootstrap.py
```

The script automatically:
- ✅ Checks for Go, Python, and Docker
- ✅ Starts PostgreSQL in a Docker container
- ✅ Builds the Go performance core (cross-platform)
- ✅ Sets up a Python virtual environment
- ✅ Installs all dependencies
- ✅ Launches the dashboard at `http://localhost:5001`

---

## 🛠 Manual Installation

If you prefer manual setup, follow these steps:

### 1. Set Up Python Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Build the Go Engine
```bash
cd src/engine-go
go build -o ../../bin/reaper-engine main.go
cd ../..
```

### 3. Configure Environment
Create a `.env` file in the root directory:
```env
AZURE_SUBSCRIPTION_ID=your-subscription-id
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
FLASK_PORT=5000
FLASK_DEBUG=True
```

### 4. Run the Application
- **CLI Mode:** `python main.py`
- **Dashboard Mode:** `python -m reaper.web.app`

---

## 🧪 Development & Quality

Cloud-Reaper maintains high professional standards. You can run the following checks:

### Linting (Ruff)
```bash
ruff check src main.py
```

### Type Checking (Mypy)
```bash
mypy src --ignore-missing-imports
```

### Testing (Pytest)
```bash
pytest
```

---

## 📋 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_SUBSCRIPTION_ID` | Your target Azure Subscription | - |
| `DATABASE_URL` | PostgreSQL Connection String | `postgresql://...` |
| `FLASK_HOST` | Host for the web dashboard | `127.0.0.1` |
| `FLASK_PORT` | Port for the web dashboard | `5000` |
| `FLASK_DEBUG` | Enable Flask debug mode | `True` |

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Ensure you run with `python -m reaper.web.app` or have `PYTHONPATH=src` |
| `Go binary not found` | Ensure you built the engine into the `bin/` directory |
| `DB Connection Refused` | Start Docker and ensure the postgres container is running |
| `az: command not found` | Install Azure CLI and ensure it is in your PATH |
| `403 Forbidden on 5000` | macOS AirPlay conflict. Use port 5001 or disable AirPlay Receiver. |

---

## 📚 Next Steps
1. Open the dashboard at `http://localhost:5000`
2. Connect your first Azure subscription in **Settings**
3. Run a **Global Scan** to identify optimization opportunities
4. Configure **Budget Guardrails** to prevent cost overruns
