# Cloud-Reaper
A high-performance FinOps engine designed to identify, quantify, and visualize infrastructure waste across multi-cloud environments. Currently optimized for **Azure-First** operations with AWS integration pending.

## 🚀 Overview
Cloud-Reaper automates the discovery of "Zombie" resources—orphaned disks, unattached volumes, and idling compute instances—calculating real-time monthly burn rates and projecting potential savings.

### Core Pillars
1. **Collectors:** Modular SDK-based discovery (Azure Compute, AWS Boto3).
2. **Engine:** Logic-driven cost calculation using customizable `price_book.yaml`.
3. **Persistence:** Time-series telemetry via InfluxDB for historical trend analysis.
4. **Visibility:** (WIP) Grafana dashboarding for "Waste Velocity" monitoring.

## 🛠 Tech Stack
- **Runtime:** Python 3.12+
- **Environment:** Ubuntu (LTS) / Debian-based
- **Cloud SDKs:** `azure-mgmt-compute`, `azure-identity`, `boto3`
- **Database:** InfluxDB v2 (Time-series)
- **Configuration:** YAML / `.env`

## 📂 Project Structure
```text
Cloud-Reaper/
├── collectors/      # Cloud-specific discovery modules
├── data/            # Persistence and InfluxDB logic
├── engine/          # Pricing data and math orchestrators
├── ui/              # Glassmorphism UI components (Dev Dashboard)
├── main.py          # Central execution orchestrator
└── .env             # Infrastructure credentials (ignored)