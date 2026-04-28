# ☁️ Cloud-Reaper
A high-performance **Hybrid FinOps Intelligence Engine** designed to bridge the gap between cloud finance and engineering action.

Cloud-Reaper uses a **Dual-Core Architecture** (Python + Go) to achieve massive scanning speeds across large-scale Azure environments, providing real-time cost reduction recommendations.

---

## 🚀 Key Features

### 1. 📊 Inform Phase (Visibility)
*   **⚡ High-Velocity Scanning:** Custom Go-based engine with Goroutines for sub-second resource auditing.
*   **🏷️ Tag Health Score:** Automated audit of critical tags (Owner, Env) for 100% cost attribution.
*   **📈 Anomaly Detection:** Real-time detection of cost spikes using 7-day moving averages via Azure Consumption SDK.

### 2. 📉 Optimize Phase (Waste Reduction)
*   **🧟 Zombie Hunting:** Identifies orphaned disks, snapshots, and idle compute resources automatically.
*   **💎 RI/SP Advisor:** Recommends Reserved Instances based on actual uptime and inventory.
*   **❄️ Cold Storage Identifier:** Scans for unused storage and suggests movement to Cool/Archive tiers.

### 3. ⚖️ Operate Phase (Governance)
*   **🛡️ Policy Guardrails:** Real-time OPA-style audit against FinOps best practices (e.g., blocking UltraSSD in Non-Prod).
*   **🚨 Budget Kill-Switch:** Automated VM deallocation safeguards for sandbox environments.

---

## 🏗 Hybrid Architecture

Cloud-Reaper leverages the strengths of two powerful languages:

1.  **Go (Performance Core):** Handles parallel API requests to Azure SDKs for lightning-fast inventory and metrics collection.
2.  **Python (Intelligence & UI):** Orchestrates the FinOps logic, cost calculation, and serves the **Cyan-Theme Glassmorphism Dashboard**.

---

## 🛠 Tech Stack
- **Languages:** Python 3.12+, Go 1.24+
- **Frontend:** HTML5, Vanilla JS, CSS (Glassmorphism & Cyan Glow)
- **Backend:** Flask, Azure SDK for Go/Python (Consumption, Storage, Monitor)
- **Design:** Modern dark-mode aesthetic with interactive micro-animations.

---

## 📂 Project Structure
```text
Cloud-Reaper/
├── collectors/      # Python-Go Bridge & Real-Time Azure SDK Modules
├── engine-go/       # High-Velocity Metric Engine (Go source)
├── engine/          # Pricing data & Intelligence logic (Python)
├── ui/              # Cyan-Theme Dashboard (Flask & JS)
├── reap.sh          # Unified Entrypoint & Bootstrapper
└── HOW_TO_RUN.md    # Detailed Setup Instructions
```

---

## 🚦 Getting Started

### The Fast Entrypoint
```bash
chmod +x reap.sh
./reap.sh  # Handles Go build, Venv creation, and app launch
```

Detailed guide: 👉 **[HOW_TO_RUN.md](HOW_TO_RUN.md)**

---

## 📝 License
MIT License. Optimized for state-of-the-art Azure FinOps.
