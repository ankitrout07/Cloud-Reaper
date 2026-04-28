# 📖 How to Run Cloud-Reaper

Cloud-Reaper is a hybrid Python/Go engine. We recommend using the **Unified Bootstrapper** (`reap.sh`) for the fastest and most reliable setup.

## 🛠 Prerequisites
- **Python 3.12+**
- **Go 1.24+**
- **Azure CLI** (`az login` required for data extraction)

---

## ⚡ The Primary Entrypoint (Linux / macOS)
The `reap.sh` script acts as a silent entrypoint that handles system checks, Go compilation, and virtual environment management automatically.

```bash
# 1. Make the script executable (One-time)
chmod +x reap.sh

# 2. Run the engine
./reap.sh
```

**What `reap.sh` does:**
1.  Verifies the `python3-venv` module is installed.
2.  Compiles the Go Performance Core (`engine-go`).
3.  Creates a virtual environment and installs dependencies from `requirements.txt`.
4.  Launches the **Cloud-Reaper Engine** (`main.py`) using the venv binary directly.

---

## 🖥 Running the FinOps Dashboard (Web UI)
To launch the interactive Glassmorphism dashboard instead of the CLI engine:

```bash
# Ensure you have run ./reap.sh at least once to build dependencies
./venv/bin/python3 ui/app.py
```
Then visit `http://localhost:5000` in your browser.

---

## 🚀 Manual Setup (Advanced)

### 1. Python Environment
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 2. Build the Go Performance Core
The Python collector detects this binary for high-speed parallel scanning:
```bash
cd engine-go
go mod tidy
go build -o reaper-engine main.go
cd ..
```

---

## 🧙‍♂️ The Onboarding Flow
1. Ensure you have run `az login` in your terminal.
2. Launch the Dashboard via `ui/app.py`.
3. If uninitialized, the UI will prompt for your **Azure Subscription ID**.
4. The system will validate your credentials and unlock the **FinOps Intelligence Suite**.

---

## 🏗 Key Environment Variables
You can set these in a `.env` file (created automatically by `reap.sh`):
- `AZURE_SUBSCRIPTION_ID`: Target subscription for scanning.
- `APP_ENV`: `production` or `development`.
- `INFLUX_TOKEN`: (Optional) For historical data persistence.

> [!TIP]
> Always ensure your Azure identity has at least **Reader** and **Cost Management Reader** permissions to unlock the full potential of the Anomaly Detection and RI Advisor modules.
