#!/bin/bash
# --- CLOUD-REAPER UBUNTU INSTALLER ---

set -e

echo "------------------------------------------------"
echo "  🛠️  SYSTEM CHECK: UBUNTU / DEBIAN"
echo "------------------------------------------------"

# 1. Check for Python VENV module (Commonly missing on fresh Ubuntu)
if ! dpkg -s python3-venv >/dev/null 2>&1; then
    echo "[!] python3-venv is missing. Installing..."
    sudo apt update && sudo apt install -y python3-venv
fi

# Resolve repo root so the script works from any working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 2. Go Build Logic
if [ -d "engine-go" ]; then
    echo "[*] Building Go Core..."
    cd engine-go && go build -o reaper-engine main.go && cd ..
else
    echo "[!] engine-go directory not found!"
    exit 1
fi

# 3. Environment Setup
if [ ! -d "venv" ]; then
    echo "[*] Creating Virtual Environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "[*] Installing dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" --quiet

# 4. Persistence Check
if [ ! -f .env ]; then
    touch .env
    echo "APP_ENV=production" > .env
fi

echo "------------------------------------------------"
echo "✅ SETUP COMPLETE. STARTING CLOUD-REAPER..."
echo "------------------------------------------------"
python3 ui/app.py
