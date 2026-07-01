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

# SQLite is used by default - no Docker container needed
echo "[*] Using SQLite database (no external database required)"

# 1. Build Go Core (Performance Engine)
if [ -d "src/engine-go" ]; then
    echo "[*] Building Go Core..."
    mkdir -p bin
    (cd src/engine-go && go build -tags cli -o ../../bin/reaper-engine .)
    echo "[+] Go engine built successfully: bin/reaper-engine"
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
./venv/bin/python -m pip install --upgrade pip --quiet
./venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt --quiet

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

# Database (SQLite - no setup required)
DATABASE_URL=sqlite:///./data/reaper.db
EOF
    echo "[+] .env file created. Please update Azure credentials!"
else
    # Check if DATABASE_URL is missing from existing .env
    if ! grep -q "^DATABASE_URL=" .env; then
        echo "[*] Adding DATABASE_URL to existing .env file..."
        echo "" >> .env
        echo "# Database (SQLite - no setup required)" >> .env
        echo "DATABASE_URL=sqlite:///./data/reaper.db" >> .env
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
    echo "    ./venv/bin/python3 -m uvicorn reaper.web.app_async:socket_app"
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
./venv/bin/python -m reaper.cli

# 6. Start Dashboard (in background)
echo "------------------------------------------------"
echo "[+] Starting Dashboard..."
echo "    Access at: http://localhost:5001"
echo "    Press Ctrl+C to stop"
echo "------------------------------------------------"
./venv/bin/python -m uvicorn reaper.web.app_async:socket_app --host 0.0.0.0 --port 5001
