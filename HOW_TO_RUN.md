# 📖 How to Run Cloud-Reaper

Cloud-Reaper is a hybrid Python/Go engine. To get the best performance, you need to ensure both environments are set up correctly.

## 🛠 Prerequisites
- **Python 3.12+**
- **Go 1.23+**
- **Azure Subscription** (with a Service Principal or logged in via Azure CLI)

## 🚀 Quick Start

### 1. Clone & Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials
Create a `.env` file in the root directory:
```env
AZURE_SUBSCRIPTION_ID=your_subscription_id
# If not using 'az login', add these:
AZURE_CLIENT_ID=your_client_id
AZURE_CLIENT_SECRET=your_client_secret
AZURE_TENANT_ID=your_tenant_id
```

### 3. Build the High-Velocity Go Engine (CRITICAL)
For the fastest performance, you must compile the Go-based metric engine:
```bash
cd engine-go
go mod tidy
go build -o reaper-engine main.go
cd ..
```
*Note: The Python collector will automatically detect this binary and use it for parallel scanning.*

### 4. Run the Orchestrator
```bash
python main.py
```

---

## 📊 Running the UI Dashboard
Cloud-Reaper includes a Glassmorphism web dashboard for visualization.
```bash
python ui/app.py
```
Then visit `http://localhost:5000` in your browser.

---

## 🏗 Architecture Note
- **Python:** Handles orchestration, CLI, and UI.
- **Go:** Handles high-concurrency metric collection from Azure.
- **InfluxDB:** (Optional) Used for persisting historical data if configured.

> [!IMPORTANT]
> If you don't build the Go engine, Cloud-Reaper will fall back to "Slow Mode" using pure Python, which may take significantly longer for large environments.
