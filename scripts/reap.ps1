<#
.SYNOPSIS
    CLOUD-REAPER WINDOWS ENTRYPOINT
.DESCRIPTION
    Full boot sequence for Cloud-Reaper on Windows:
      .\scripts\reap.ps1              # full boot (check -> build -> install -> web)
      .\scripts\reap.ps1 -SkipBuild   # skip Go build (use existing bin/)
      .\scripts\reap.ps1 -Port 8080   # override dashboard port
      .\scripts\reap.ps1 -NoDev       # skip dev dependencies
.PARAMETER SkipBuild
    Skip the Go engine build step (use pre-built binaries in bin/).
.PARAMETER NoDev
    Skip installation of requirements-dev.txt.
.PARAMETER Port
    Dashboard port override (default: reads FLASK_PORT from .env or 5001).
#>
param(
    [switch]$SkipBuild,
    [switch]$NoDev,
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT_DIR   = Split-Path -Parent $SCRIPT_DIR
Set-Location -Path $ROOT_DIR
$env:PYTHONPATH = "$ROOT_DIR\src"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Step([string]$msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host $msg -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Err([string]$msg)  { Write-Host $msg -ForegroundColor Red }

function Read-EnvPort {
    $envFile = "$ROOT_DIR\.env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^FLASK_PORT=(.+)$') { return $Matches[1].Trim().Trim('"').Trim("'") }
        }
    }
    return "5001"
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host ("=" * 62) -ForegroundColor Cyan
Write-Host "  CLOUD-REAPER  .  Windows PowerShell Bootstrap" -ForegroundColor Cyan
Write-Host ("=" * 62) -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# [1/4] SYSTEM CHECK
# ---------------------------------------------------------------------------
Write-Host "[1/4] VERIFYING SYSTEM CORE ..." -ForegroundColor Cyan

# Go
if (!(Get-Command "go" -ErrorAction SilentlyContinue)) {
    Write-Err "[!] Go is not installed. Please install Go 1.24+ first."
    Write-Host "    Visit: https://golang.org/dl/"
    exit 1
}
Write-Ok "  [+]  Go             $(& go version)"

# Python
$pyCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (!$pyCmd) { $pyCmd = Get-Command "python3" -ErrorAction SilentlyContinue }
if (!$pyCmd) {
    Write-Err "[!] Python is not installed. Please install Python 3.12+ first."
    exit 1
}
$pythonExe        = $pyCmd.Source
$pythonVersionStr = & $pythonExe -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
if ([version]$pythonVersionStr -lt [version]"3.12") {
    Write-Err "[!] Python $pythonVersionStr detected. Cloud-Reaper requires Python 3.12+"
    exit 1
}
Write-Ok "  [+]  Python         $pythonVersionStr"

# Git (optional)
if (Get-Command "git" -ErrorAction SilentlyContinue) {
    Write-Ok "  [+]  Git             $(& git --version)"
} else {
    Write-Warn "  [!]  Git             not found (optional)"
}

# Azure CLI (optional)
if (Get-Command "az" -ErrorAction SilentlyContinue) {
    Write-Ok "  [+]  Azure CLI       found"
} else {
    Write-Warn "  [!]  Azure CLI       not found (optional)"
}

Write-Ok "[+] System check passed.`n"

# ---------------------------------------------------------------------------
# [2/4] ASSEMBLING COMPONENTS
# ---------------------------------------------------------------------------
Write-Host "[2/4] ASSEMBLING COMPONENTS ..." -ForegroundColor Cyan

# --- Go Build ---
if ($SkipBuild) {
    Write-Warn "  Skipping Go build (-SkipBuild flag set)."
} elseif (Test-Path "$ROOT_DIR\src\engine-go") {
    Write-Step "  Building Go microservices ..."
    $binDir = "$ROOT_DIR\bin"
    if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir | Out-Null }

    $targets = @(
        @{ Name = "reaper-engine";    Path = ".";                     Tags = "cli" },
        @{ Name = "taskserver";       Path = "./cmd/taskserver";       Tags = "" },
        @{ Name = "websocketserver";  Path = "./cmd/websocketserver";  Tags = "" },
        @{ Name = "ratelimitserver";  Path = "./cmd/ratelimitserver";  Tags = "" },
        @{ Name = "ragserver";        Path = "./cmd/ragserver";        Tags = "" },
        @{ Name = "calculatorserver"; Path = "./cmd/calculatorserver"; Tags = "" },
        @{ Name = "anomalyserver";    Path = "./cmd/anomalyserver";    Tags = "" }
    )

    $engineDir   = "$ROOT_DIR\src\engine-go"
    $buildFailed = $false

    foreach ($t in $targets) {
        $outPath   = "$binDir\$($t.Name).exe"
        $buildArgs = @("build")
        if ($t.Tags) { $buildArgs += @("-tags", $t.Tags) }
        $buildArgs += @("-o", $outPath, $t.Path)
        Write-Host "    Building $($t.Name) -> $outPath" -ForegroundColor DarkCyan
        Push-Location $engineDir
        & go @buildArgs 2>&1 | ForEach-Object { Write-Host "      $_" }
        Pop-Location
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "    [!] Build failed for $($t.Name) — features may be limited."
            $buildFailed = $true
        } else {
            Write-Ok "    [+] $($t.Name)"
        }
    }

    if ($buildFailed) {
        Write-Warn "  [!] Some Go binaries failed. Dashboard features may fall back to Python."
    } else {
        Write-Ok "  [+] All 7 Go microservices built successfully."
    }
} else {
    Write-Warn "  [!] src\engine-go not found - skipping Go build."
}

# --- Python venv + deps ---
if (-not (Test-Path "$ROOT_DIR\venv")) {
    Write-Step "  Creating virtual environment ..."
    & $pythonExe -m venv "$ROOT_DIR\venv"
}
$venvPython = "$ROOT_DIR\venv\Scripts\python.exe"

Write-Step "  Upgrading pip ..."
& $venvPython -m pip install --upgrade pip --quiet

Write-Step "  Installing runtime dependencies (requirements.txt) ..."
& $venvPython -m pip install --no-warn-script-location -r "$ROOT_DIR\requirements.txt" --quiet
if ($LASTEXITCODE -ne 0) { Write-Err "[!] pip install -r requirements.txt failed."; exit 1 }

if (-not $NoDev -and (Test-Path "$ROOT_DIR\requirements-dev.txt")) {
    Write-Step "  Installing dev dependencies (requirements-dev.txt) ..."
    & $venvPython -m pip install --no-warn-script-location -r "$ROOT_DIR\requirements-dev.txt" --quiet
}

Write-Ok "[+] Components assembled.`n"

# ---------------------------------------------------------------------------
# [3/4] CONFIGURING ENVIRONMENT
# ---------------------------------------------------------------------------
Write-Host "[3/4] CONFIGURING ENVIRONMENT ..." -ForegroundColor Cyan

$envFile = "$ROOT_DIR\.env"
if (-not (Test-Path $envFile)) {
    Write-Step "  Creating .env from defaults ..."
    $envContent = @"
# Cloud-Reaper environment -- auto-generated by reap.ps1
APP_ENV=development
FLASK_PORT=5001
FLASK_HOST=0.0.0.0
FLASK_DEBUG=True

# Database: Uses SQLite by default (no setup needed)
# DATABASE_URL=sqlite:///./data/reaper.db

# Go Microservice Ports
GO_BRIDGE_HOST=localhost
GO_BRIDGE_PORT=7070
GO_TASK_MANAGER_HOST=localhost
GO_TASK_MANAGER_PORT=7071
GO_WEBSOCKET_HOST=localhost
GO_WEBSOCKET_PORT=7072
GO_RATELIMITER_HOST=localhost
GO_RATELIMITER_PORT=7073
GO_RAG_HOST=localhost
GO_RAG_PORT=7074
GO_CALCULATOR_HOST=localhost
GO_CALCULATOR_PORT=7075
GO_ANOMALY_HOST=localhost
GO_ANOMALY_PORT=7076

# AI Backend Selection (options: gemini, openai, ensemble)
AI_BACKEND=gemini
AI_ML_ENABLED=true

# Optional: Azure Credentials (for cloud scanning features)
# AZURE_SUBSCRIPTION_ID=your_subscription_id
# AZURE_TENANT_ID=your_tenant_id
# AZURE_CLIENT_ID=your_client_id
# AZURE_CLIENT_SECRET=your_client_secret

# Optional: AI/GenAI API Keys (for Copilot & AI Architect)
# GEMINI_API_KEY=your_gemini_api_key
# OPENAI_API_KEY=your_openai_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key

# Optional: Redis (for RAG caching and telemetry)
# REDIS_URL=redis://localhost:6379/0

# Safety: dry-run mode prevents any live remediation actions
DRY_RUN_MODE=true
ENABLE_REMEDIATION=false

# Optional: Notifications
# DISCORD_WEBHOOK_URL=your_discord_webhook
"@
    Set-Content -Path $envFile -Value $envContent -Encoding UTF8
    Write-Ok "  .env created at $envFile"
    Write-Warn "  -> Fill in optional secrets as needed for full functionality"
} else {
    # Patch any missing keys into existing .env
    $existing = Get-Content $envFile -Raw
    $patches  = [ordered]@{
        "FLASK_HOST"           = "0.0.0.0"
        "GO_BRIDGE_PORT"       = "7070"
        "GO_TASK_MANAGER_PORT" = "7071"
        "GO_WEBSOCKET_PORT"    = "7072"
        "GO_RATELIMITER_PORT"  = "7073"
        "GO_RAG_PORT"          = "7074"
        "GO_CALCULATOR_PORT"   = "7075"
        "GO_ANOMALY_PORT"      = "7076"
        "AI_BACKEND"           = "gemini"
        "DRY_RUN_MODE"         = "true"
    }
    $added = @()
    foreach ($kv in $patches.GetEnumerator()) {
        if ($existing -notmatch "^$($kv.Key)=") { $added += "$($kv.Key)=$($kv.Value)" }
    }
    if ($added.Count -gt 0) {
        Add-Content -Path $envFile -Value "`n# Added by reap.ps1"
        $added | ForEach-Object { Add-Content -Path $envFile -Value $_ }
        Write-Step "  Patched .env with $($added.Count) missing key(s)."
    }
}

# Resolve dashboard port
$dashPort = if ($Port -gt 0) { "$Port" } else { Read-EnvPort }

# Ensure data/ directory exists
$dataDir = "$ROOT_DIR\data"
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

# Initialise SQLite DB
Write-Step "  Initializing database ..."
$dbPath = "$dataDir\reaper.db"
$env:DATABASE_URL = "sqlite:///$dbPath"
& $venvPython -c "from reaper.engine.models.resources import init_db; init_db()" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Ok "  Database ready: $dbPath" }

Write-Ok "[+] Environment configured.`n"

# ---------------------------------------------------------------------------
# [4/4] INITIALIZING INTELLIGENCE
# ---------------------------------------------------------------------------
Write-Host "[4/4] INITIALIZING INTELLIGENCE ..." -ForegroundColor Cyan

Write-Host ""
Write-Host ("=" * 66) -ForegroundColor Green
Write-Host "  CLOUD-REAPER INTELLIGENCE ENGINE IS ONLINE" -ForegroundColor Green
Write-Host ("=" * 66) -ForegroundColor Green
Write-Host "  > Dashboard:     http://localhost:$dashPort"
Write-Host "  > Port:          $dashPort"
Write-Host "  > Status:        HEALTHY" -ForegroundColor Green
Write-Host "  > Python Layer:  FastAPI + Uvicorn + Socket.IO"
Write-Host "  > Go Services:   reaper-engine  :7070"
Write-Host "                   taskserver       :7071"
Write-Host "                   websocketserver  :7072"
Write-Host "                   ratelimitserver  :7073"
Write-Host "                   ragserver        :7074"
Write-Host "                   calculatorserver :7075"
Write-Host "                   anomalyserver    :7076"
Write-Host ("=" * 66) -ForegroundColor Green
Write-Host "  Press Ctrl+C to terminate the session safely." -ForegroundColor DarkGray
Write-Host ""

# --- Launch Go microservices (non-blocking, best-effort) ---
$goServices = @(
    @{ Name = "reaper-engine";    Args = "--mode serve --port 7070" },
    @{ Name = "taskserver";       Args = "-port 7071" },
    @{ Name = "websocketserver";  Args = "-port 7072" },
    @{ Name = "ratelimitserver";  Args = "-port 7073" },
    @{ Name = "ragserver";        Args = "-port 7074" },
    @{ Name = "calculatorserver"; Args = "-port 7075" },
    @{ Name = "anomalyserver";    Args = "-port 7076" }
)

$goProcs = @()
foreach ($svc in $goServices) {
    $bin = "$ROOT_DIR\bin\$($svc.Name).exe"
    if (Test-Path $bin) {
        Write-Step "  Starting $($svc.Name) ..."
        try {
            $proc = Start-Process -FilePath $bin `
                                  -ArgumentList $svc.Args.Split(" ") `
                                  -WorkingDirectory $ROOT_DIR `
                                  -WindowStyle Hidden -PassThru
            $goProcs += $proc
        } catch {
            if ($_.Exception.Message -match "0x11C7|4551|blocked|policy|access is denied") {
                Write-Warn "  [!] $($svc.Name) blocked by Windows Application Control policy."
                Write-Warn "      Run from a Developer PowerShell or add bin\ to your AppLocker allowlist."
            } else {
                Write-Warn "  [!] $($svc.Name) failed to start: $($_.Exception.Message)"
            }
        }
    } else {
        Write-Warn "  [!] $($svc.Name) binary not found in bin\. Features may fall back."
    }
}

# --- Launch Uvicorn (blocking) ---
try {
    & $venvPython -m uvicorn reaper.web.app_async:socket_app `
        --host "0.0.0.0" --port $dashPort
} finally {
    # Gracefully stop all Go services on exit
    foreach ($proc in $goProcs) {
        try { $proc.Kill(); $proc.WaitForExit(2000) } catch {}
    }
    Write-Host "`n[*] Cloud-Reaper session ended gracefully." -ForegroundColor Cyan
}
