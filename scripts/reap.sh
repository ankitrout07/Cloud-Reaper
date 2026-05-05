#!/bin/bash
# --- CLOUD-REAPER LINUX ENTRYPOINT ---

set -e

# Resolve repo root so the script works from any working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# Set PYTHONPATH to include src directory
export PYTHONPATH="$PYTHONPATH:$ROOT_DIR/src"

echo "------------------------------------------------"
echo "  🛠️  SYSTEM CHECK & INITIALIZATION"
echo "------------------------------------------------"

# 0. Check for required tools
echo "[*] Checking system requirements..."

# Check if Go is installed
if ! command -v go &> /dev/null; then
    echo "[!] Go is not installed. Please install Go 1.24+ first."
    echo "   Visit: https://golang.org/dl/"
    exit 1
fi

# Check if Python 3.12+ is installed
if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 is not installed. Please install Python 3.12+ first."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if [[ "$(printf '%s\n' "$PYTHON_VERSION" "3.12" | sort -V | head -n1)" != "3.12" ]]; then
    echo "[!] Python $PYTHON_VERSION detected. Cloud-Reaper requires Python 3.12+"
    exit 1
fi

# Check if Docker is available for PostgreSQL
if command -v docker &> /dev/null; then
    echo "[*] Docker found - checking PostgreSQL container..."
    if ! docker ps | grep -q cloud-reaper-db; then
        echo "[*] Starting PostgreSQL container..."
        docker run --name cloud-reaper-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres >/dev/null 2>&1 || true
        echo "[*] Waiting for PostgreSQL to be ready..."
        sleep 3
    fi
else
    echo "[!] Docker not found. Please install Docker or start PostgreSQL manually."
fi

# 1. Build Go Core (Performance Engine)
if [ -d "src/engine-go" ]; then
    echo "[*] Building Go Core..."
    (cd src/engine-go && go build -o reaper-engine main.go)
    echo "[+] Go engine built successfully"
else
    echo "[!] src/engine-go directory not found!"
    exit 1
fi

# 2. Virtual Environment & Dependency Management
if [ ! -d "venv" ]; then
    echo "[*] Creating Virtual Environment..."
    python3 -m venv venv
fi

echo "[*] Activating virtual environment and installing/updating dependencies..."
./venv/bin/pip install --upgrade pip --quiet
./venv/bin/pip install -r requirements.txt -r requirements-dev.txt --quiet

# 3. Environment Configuration
if [ ! -f .env ]; then
    echo "[*] Creating .env file..."
    cat > .env << 'EOF'
# Cloud-Reaper Configuration
APP_ENV=development

# Azure Credentials (Update with your values)
AZURE_SUBSCRIPTION_ID=your_subscription_id
AZURE_TENANT_ID=your_tenant_id
AZURE_CLIENT_ID=your_client_id
AZURE_CLIENT_SECRET=your_client_secret

# Database (PostgreSQL via Docker)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres

# InfluxDB (Optional - for metrics storage)
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_token
INFLUXDB_ORG=ReaperOps
INFLUXDB_BUCKET=cloud_burn
EOF
    echo "[+] .env file created. Please update Azure credentials!"
else
    # Check if DATABASE_URL is missing from existing .env
    if ! grep -q "^DATABASE_URL=" .env; then
        echo "[*] Adding DATABASE_URL to existing .env file..."
        echo "" >> .env
        echo "# Database (PostgreSQL via Docker)" >> .env
        echo "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres" >> .env
    fi
fi

# 4. Validate Azure Configuration
if grep -q "your_subscription_id" .env; then
    echo ""
    echo "=================================================="
    echo "             CLOUD REAPER v1.0 [AZURE MODE]"
    echo "=================================================="
    echo ""
    echo "[!] CONFIGURATION ERROR: Azure Subscription ID is invalid."
    echo "    Current ID: your_subscription_id"
    echo ""
    echo "    Please update your .env file with a real Subscription ID."
    echo "    Or launch the Dashboard to use the Onboarding Wizard:"
    echo "    ./venv/bin/python3 -m reaper.web.app"
    echo ""
    echo "=================================================="
    echo ""
    exit 1
fi

echo "------------------------------------------------"
echo "✅ ENVIRONMENT READY. STARTING CLOUD-REAPER..."
echo "------------------------------------------------"

# 5. Run CLI Scan
echo "[*] Running resource scan..."
./venv/bin/python3 -m reaper.cli

# 6. Start Dashboard (in background)
echo "------------------------------------------------"
echo "[+] Starting Dashboard..."
echo "    Access at: http://localhost:5000"
echo "    Press Ctrl+C to stop"
echo "------------------------------------------------"
./venv/bin/python3 -m reaper.web.app
