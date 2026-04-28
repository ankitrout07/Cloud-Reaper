# 📖 How to Run Cloud-Reaper

Cloud-Reaper is a hybrid Python/Go engine. To get the best performance, you need to ensure both environments are set up correctly. We now provide an automated bootstrapper for the fastest setup.

## 🛠 Prerequisites
- **Python 3.12+**
- **Go 1.23+**
- **Azure CLI** (`az login` highly recommended)

---

## ⚡ The Fast Way (Ubuntu / Linux)
We provide a unified bootstrapper that handles system dependency checks, Go compilation, and virtual environment setup in one command.

```bash
# Make the script executable
chmod +x reap.sh

# Run the bootstrapper
./reap.sh
```

---

## 🚀 Manual Setup (Other Platforms)

### 1. Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Build the High-Velocity Go Engine (CRITICAL)
For the fastest performance, you must compile the Go-based metric engine:
```bash
cd engine-go
go mod tidy
go build -o reaper-engine main.go
cd ..
```
*Note: The Python collector will automatically detect this binary and use it for parallel scanning.*

### 3. Run the Dashboard
```bash
python3 ui/app.py
```
Then visit `http://localhost:5000` in your browser.

---

## 🧙‍♂️ The Onboarding Wizard
If this is your first time running Cloud-Reaper, the UI will automatically launch the **Onboarding Wizard**.

1. Ensure you have run `az login` in your terminal.
2. Enter your **Azure Subscription ID** when prompted by the blur-overlay.
3. The system will test the connection in real-time.
4. Once initialized, the dashboard will unlock.

---

## 🏗 Architecture Note
- **Python:** Handles orchestration, CLI, and UI.
- **Go:** Handles high-concurrency metric collection from Azure.
- **InfluxDB:** (Optional) Used for persisting historical data if configured.

> [!IMPORTANT]
> If you don't build the Go engine (via `./reap.sh` or manual build), Cloud-Reaper will fall back to "Slow Mode" using pure Python, which may take significantly longer for large environments.
