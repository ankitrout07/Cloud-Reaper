# ☁️ Cloud-Reaper

A high-performance **Hybrid FinOps Intelligence Engine** designed to bridge the gap between cloud finance and engineering action.

Cloud-Reaper uses a **Dual-Core Architecture** (Python + Go) to achieve massive scanning speeds across large-scale Azure environments, providing real-time cost reduction recommendations.

---

## 🚀 Key Features

### 1. 📊 Inform Phase (Visibility)
*   **⚡ High-Velocity Scanning:** Custom Go-based engine with Goroutines for sub-second resource auditing.
*   **🏷️ Tag Health Score:** Automated audit of critical tags (Owner, Env) for 100% cost attribution.
*   **📈 Anomaly Detection:** Real-time detection of cost spikes using seasonal-aware ARIMA forecasting.

### 2. 📉 Optimize Phase (Waste Reduction)
*   **🧟 Zombie Hunting:** Identifies orphaned disks, snapshots, and idle compute resources automatically.
*   **💎 RI/SP Advisor:** Recommends Reserved Instances based on actual uptime and inventory.
*   **❄️ Cold Storage Identifier:** Scans for unused storage and suggests movement to Cool/Archive tiers.

### 3. ⚖️ Operate Phase (Governance)
*   **🛡️ Policy Guardrails:** Real-time audit against FinOps best practices.
*   **🚨 Budget Kill-Switch:** Automated VM deallocation safeguards for sandbox environments.
*   **🔑 Multi-Tenant Connect:** Support for high-velocity scanning via **Azure Service Principals**.

---

## 🏗 Hybrid Architecture

Cloud-Reaper leverages the strengths of two powerful languages:

1.  **Go (Performance Core):** Handles parallel API requests to Azure SDKs for lightning-fast inventory collection.
2.  **Python (Intelligence & UI):** Orchestrates the FinOps logic, cost calculation, and serves the **Cyan-Theme Dashboard**.

---

## 📂 Project Structure

The project follows a professional, modular structure:

```text
Cloud-Reaper/
├── src/
│   ├── reaper/         # Python Intelligence & Web Layer
│   │   ├── collectors/ # Azure/AWS Scrapers & Auth
│   │   ├── engine/     # FinOps Models, Logic & DB
│   │   └── web/        # Flask App & UI Templates
│   └── engine-go/      # Go High-Velocity Performance Core
├── scripts/            # Bootstrapping & Utility Scripts
├── tests/              # Comprehensive Test Suite
├── pyproject.toml      # Modern Python Configuration (Ruff, Mypy, Pytest)
└── main.py             # Global Entry Point
```

---

## 🛠 Tech Stack
- **Languages:** Python 3.12+, Go 1.24+
- **Database:** PostgreSQL (with SQLAlchemy 2.0 type safety)
- **Frontend:** HTML5, Vanilla JS, CSS (Glassmorphism & Cyan Glow)
- **Quality Gates:** 
    - **Python:** Ruff (Linting), Mypy (Type Safety), Pytest (Testing)
    - **Go:** Golangci-lint (Static Analysis)

---

## 🚦 Getting Started

### ⚡ Quick Start

```bash
# Clone the repository
git clone https://github.com/ankitrout07/Cloud-Reaper.git
cd Cloud-Reaper

# Run the universal bootstrap script (macOS, Windows, Linux)
python bootstrap.py
```

The dashboard will be available at **http://localhost:5001**.

### Professional Entry Points
- **Web Dashboard:** `python -m reaper.web.app`
- **CLI Scanner:** `python main.py`
- **Go Engine (Direct):** `./bin/reaper-engine --help`

Detailed setup guide: 👉 **[HOW_TO_RUN.md](HOW_TO_RUN.md)**

---

## 📝 License
MIT License. Optimized for state-of-the-art Azure FinOps.
