# Cloud-Reaper Deployment and Operations

This guide outlines deployment strategies, container setups, and environment variable requirements for operationalizing **Cloud-Reaper**.

## Local Quickstart Setup

Cloud-Reaper includes a universal `bootstrap.py` script to automate multi-platform workspace setup. To spin up the system locally:

```bash
python bootstrap.py --dev
```

This script performs the following steps:
1. Detects host system architecture and checks Go 1.24+ / Python 3.12+ installations.
2. Initializes a local Python virtual environment (`venv`) and installs base packages.
3. Launches a docker-compose container stack containing PostgreSQL and Redis.
4. Generates a default `.env` configuration file.

## Docker Container Deployment

For production clusters, we build and run Cloud-Reaper using multi-stage containerization:

```bash
docker-compose up --build -d
```

### Environment Variables (.env)

The following configuration parameters must be supplied to the container runtime:
- `GEMINI_API_KEY`: API access key for structural model generations and RAG vector searches.
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`: PostgreSQL credential mapping targets.
- `VAULT_ENCRYPTION_KEY`: Cryptographic salt token used to secure secondary cloud provider access details in the SQLite/Postgres credentials vault.
- `REAPER_METRICS_EMIT_SEC`: Timing interval for WebSocket telemetry broadcasts down to the active dashboard.
