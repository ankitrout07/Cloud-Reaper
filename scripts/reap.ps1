<#
.SYNOPSIS
CLOUD-REAPER WINDOWS ENTRYPOINT
#>

$ErrorActionPreference = "Stop"

# Resolve repo root so the script works from any working directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT_DIR = Split-Path -Parent $SCRIPT_DIR
Set-Location -Path $ROOT_DIR

# Set PYTHONPATH to include src directory
$env:PYTHONPATH = "$env:PYTHONPATH;$ROOT_DIR\src"

Write-Host "------------------------------------------------"
Write-Host "  🛠️  SYSTEM CHECK & INITIALIZATION"
Write-Host "------------------------------------------------"

# 0. Check for required tools
Write-Host "[*] Checking system requirements..."

# Check if Go is installed
if (!(Get-Command "go" -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Go is not installed. Please install Go 1.24+ first." -ForegroundColor Red
    Write-Host "   Visit: https://golang.org/dl/"
    exit 1
}

# Check if Python is installed
if (!(Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Python is not installed. Please install Python 3.12+ first." -ForegroundColor Red
    exit 1
}

# Check Python version
$pythonVersionStr = & python -c 'import sys; print(".".join(map(str, sys.version_info[:2])))'
$pythonVersion = [version]$pythonVersionStr
if ($pythonVersion -lt [version]"3.12") {
    Write-Host "[!] Python $pythonVersionStr detected. Cloud-Reaper requires Python 3.12+" -ForegroundColor Red
    exit 1
}

# SQLite is used by default - no Docker container needed
Write-Host "[*] Using SQLite database (no external database required)"

# 1. Build Go Core (Performance Engine)
if (Test-Path "src\engine-go") {
    Write-Host "[*] Building Go Core..."
    Set-Location "src\engine-go"
    & go build -o reaper-engine.exe main.go
    Set-Location $ROOT_DIR
    Write-Host "[+] Go engine built successfully"
} else {
    Write-Host "[!] src\engine-go directory not found!" -ForegroundColor Red
    exit 1
}

# 2. Virtual Environment & Dependency Management
if (-not (Test-Path "venv")) {
    Write-Host "[*] Creating Virtual Environment..."
    & python -m venv venv
}

Write-Host "[*] Activating virtual environment and installing/updating dependencies..."
& .\venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\venv\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt --quiet

# 3. Environment Configuration
if (-not (Test-Path ".env")) {
    Write-Host "[*] Creating .env file..."
    $envContent = @"
# Cloud-Reaper Configuration
APP_ENV=development

# Azure Credentials (Update with your values)
AZURE_SUBSCRIPTION_ID=your_subscription_id
AZURE_TENANT_ID=your_tenant_id
AZURE_CLIENT_ID=your_client_id
AZURE_CLIENT_SECRET=your_client_secret

# Database (SQLite - no setup required)
DATABASE_URL=sqlite:///./data/reaper.db

# Flask Web Dashboard
FLASK_PORT=5001
FLASK_DEBUG=True
"@
    Set-Content -Path ".env" -Value $envContent
    Write-Host "[+] .env file created. Please update Azure credentials!"
} else {
    # Check if DATABASE_URL is missing from existing .env
    $envFileContent = Get-Content ".env"
    if (-not ($envFileContent -match "^DATABASE_URL=")) {
        Write-Host "[*] Adding DATABASE_URL to existing .env file..."
        Add-Content -Path ".env" -Value ""
        Add-Content -Path ".env" -Value "# Database (SQLite - no setup required)"
        Add-Content -Path ".env" -Value "DATABASE_URL=sqlite:///./data/reaper.db"
    }
}

# 4. Validate Azure Configuration
$envFileContent = Get-Content ".env"
if ($envFileContent -match "your_subscription_id") {
    Write-Host ""
    Write-Host "=================================================="
    Write-Host "             CLOUD REAPER v1.0 [AZURE MODE]"
    Write-Host "=================================================="
    Write-Host ""
    Write-Host "[!] CONFIGURATION ERROR: Azure Subscription ID is invalid." -ForegroundColor Red
    Write-Host "    Current ID: your_subscription_id"
    Write-Host ""
    Write-Host "    Please update your .env file with a real Subscription ID."
    Write-Host "    Or launch the Dashboard to use the Onboarding Wizard:"
    Write-Host "    .\venv\Scripts\python.exe -m uvicorn reaper.web.app_async:socket_app"
    Write-Host ""
    Write-Host "=================================================="
    Write-Host ""
    exit 1
}

Write-Host "------------------------------------------------"
Write-Host "✅ ENVIRONMENT READY. STARTING CLOUD-REAPER..."
Write-Host "------------------------------------------------"

# 5. Run CLI Scan
Write-Host "[*] Running resource scan..."
& .\venv\Scripts\python.exe -m reaper.cli

# 6. Start Dashboard
Write-Host "------------------------------------------------"
Write-Host "[+] Starting Dashboard..."
Write-Host "    Access at: http://localhost:5001"
Write-Host "    Press Ctrl+C to stop"
Write-Host "------------------------------------------------"
& .\venv\Scripts\python.exe -m uvicorn reaper.web.app_async:socket_app --host 0.0.0.0 --port 5001
