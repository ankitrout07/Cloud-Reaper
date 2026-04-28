#!/bin/bash
# --- CLOUD-REAPER UBUNTU ENTRYPOINT ---

set -e

# Resolve repo root so the script works from any working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "------------------------------------------------"
echo "  🛠️  SYSTEM CHECK & INITIALIZATION"
echo "------------------------------------------------"

# 1. Ensure Python VENV is available
if ! dpkg -s python3-venv >/dev/null 2>&1; then
    echo "[!] python3-venv is missing. Installing..."
    sudo apt update && sudo apt install -y python3-venv
fi

# 2. Build Go Core (Performance Engine)
if [ -d "engine-go" ]; then
    echo "[*] Building Go Core..."
    (cd engine-go && go build -o reaper-engine main.go)
else
    echo "[!] engine-go directory not found!"
    exit 1
fi

# 3. Virtual Environment & Dependency Management
if [ ! -d "venv" ]; then
    echo "[*] Creating Virtual Environment..."
    python3 -m venv venv
    echo "[*] Installing dependencies..."
    ./venv/bin/pip install -r requirements.txt --quiet
fi

# 4. Persistence & Configuration
if [ ! -f .env ]; then
    touch .env
    echo "APP_ENV=production" > .env
fi

echo "------------------------------------------------"
echo "✅ ENVIRONMENT READY. STARTING CLOUD-REAPER..."
echo "------------------------------------------------"

# 5. Run CLI Scan
./venv/bin/python3 main.py

# 6. Start Dashboard
echo "------------------------------------------------"
echo "[+] Starting Dashboard..."
./venv/bin/python3 ui/app.py
