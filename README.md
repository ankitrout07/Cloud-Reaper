# ☁️ Cloud-Reaper

A high-performance **Hybrid FinOps Engine** designed to identify, quantify, and visualize infrastructure waste across multi-cloud environments. 

Cloud-Reaper uses a **Dual-Core Architecture** (Python + Go) to achieve massive scanning speeds across large-scale Azure environments.

---

## 🚀 Key Features

*   **⚡ High-Velocity Scanning:** Uses a custom **Go-based engine** with Goroutines to scan hundreds of VMs and Disks in parallel.
*   **🧟 Zombie Resource Detection:** Automatically identifies orphaned disks and unattached volumes.
*   **📉 Idle Compute Discovery:** Detects under-utilized VMs with CPU usage < 5% over the last hour.
*   **💰 Cost Projection:** Real-time monthly burn rate calculations using custom `price_book.yaml`.
*   **🎨 Glassmorphism UI:** A modern, interactive dashboard for real-time waste visualization.

---

## 🏗 Hybrid Architecture

Cloud-Reaper leverages the strengths of two powerful languages:

1.  **Go (Performance Core):** Handles the "heavy lifting" of making hundreds of parallel API requests to Cloud SDKs for inventory and metrics.
2.  **Python (Logic & UI):** Handles the orchestration, cost calculation logic, CLI interface, and the Flask-based web dashboard.

### Performance Comparison
| Operation | Pure Python | Hybrid (Go + Python) | Speedup |
| :--- | :--- | :--- | :--- |
| Metric Scan (100 VMs) | ~150s | **~5-10s** | **20x** |

---

## 🛠 Tech Stack
- **Languages:** Python 3.12+, Go 1.23+
- **Frameworks:** Flask (UI), Azure SDK for Go/Python
- **Data Persistence:** InfluxDB v2 (Time-series)
- **Design:** CSS Glassmorphism + Vanilla JS

---

## 📂 Project Structure
```text
Cloud-Reaper/
├── collectors/      # Python-Go Bridge & Cloud Modules
├── engine-go/       # High-Velocity Metric Engine (Go source)
├── engine/          # Pricing data & Cost logic (Python)
├── ui/              # Glassmorphism Dashboard (Flask)
├── main.py          # CLI Orchestrator
└── HOW_TO_RUN.md    # Detailed Setup Instructions
```

---

## 🚦 Getting Started

To get the system up and running, please refer to the detailed guide in:
👉 **[HOW_TO_RUN.md](HOW_TO_RUN.md)**

### Quick Build
```bash
# Build the Go core
cd engine-go && go build -o reaper-engine main.go && cd ..

# Run the app
python main.py
```

---

## 📝 License
MIT License. Optimized for Azure-First environments.