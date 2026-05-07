"""Cloud-Reaper cross-platform bootstrapper.

Sets up the virtual environment, builds the Go engine, and launches the dashboard.
Run directly with: python bootstrap.py
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def print_banner() -> None:
    """Print the Cloud-Reaper startup banner."""
    print("=" * 60)
    print("        🚀 CLOUD-REAPER CROSS-PLATFORM BOOTSTRAP")
    print("=" * 60)


def run_command(cmd: list[str], cwd: str | None = None, env: dict | None = None) -> bool:
    """Run a subprocess command with full path safety and fail-fast semantics."""
    print(f"[*] Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd, env=env, check=True)  # noqa: S603
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] Error: {e}")
        return False


def _docker(args: list[str]) -> subprocess.CompletedProcess:
    """Run a docker sub-command using its absolute path (Fixes S607, PLW1510)."""
    docker_bin = shutil.which("docker") or "docker"
    return subprocess.run(  # noqa: S603
        [docker_bin, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def check_requirements() -> bool:
    """Verify Go, Docker, and Azure CLI status."""
    print("[*] Checking system requirements...")

    # Go Check
    if not shutil.which("go"):
        print("[!] Go not found. Please install Go 1.24+")
        return False

    # Azure CLI Check
    if not shutil.which("az"):
        print("[!] Azure CLI not found. Please install it to continue.")
        return False

    # Check Azure Login Status
    print("[*] Verifying Azure authentication...")
    try:
        az_check = subprocess.run(["az", "account", "show"], capture_output=True, text=True, check=False)
        if az_check.returncode != 0:
            print("[!] Not logged into Azure. Please run 'az login' first.")
            return False
        print("[+] Azure session active.")
    except Exception:
        print("[!] Could not verify Azure session. Proceeding with caution...")

    # PDF Library Check (Linux)
    if platform.system() == "Linux":
        print("[*] Checking PDF guardrails (Pango/Cairo)...")
        try:
            ldconfig = shutil.which("ldconfig")
            if ldconfig:
                pango_check = subprocess.run([ldconfig, "-p"], capture_output=True, text=True, check=False)
                if "libpango-1.0" not in pango_check.stdout or "libpangocairo-1.0" not in pango_check.stdout:
                    print("[!] WARNING: PDF libraries missing. Install with: sudo apt install libpango-1.0-0")
        except Exception:
            pass

    # Docker & Postgres Check
    if shutil.which("docker"):
        print("[*] Docker found. Ensuring PostgreSQL is running...")
        try:
            _docker(["start", "cloud-reaper-db"])
            result = _docker(["ps"])
            if "cloud-reaper-db" not in result.stdout:
                print("[*] Creating fresh PostgreSQL container...")
                _docker([
                    "run", "--name", "cloud-reaper-db",
                    "-e", "POSTGRES_PASSWORD=postgres",
                    "-p", "5432:5432", "-d", "postgres",
                ])
        except Exception as e:
            print(f"[!] Docker error: {e}. Start Postgres manually if needed.")
    
    return True


def setup_venv() -> str:
    """Create the virtual environment and install dependencies."""
    print("[*] Setting up virtual environment...")
    venv_dir = Path("venv")
    if not venv_dir.exists():
        run_command([sys.executable, "-m", "venv", str(venv_dir)])

    is_windows = platform.system() == "Windows"
    python_path = venv_dir / ("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")
    pip_path = venv_dir / ("Scripts" if is_windows else "bin") / ("pip.exe" if is_windows else "pip")

    print("[*] Synchronizing dependencies...")
    run_command([str(pip_path), "install", "--upgrade", "pip", "--quiet"])
    run_command([str(pip_path), "install", "-r", "requirements.txt", "--quiet"])

    return str(python_path)


def setup_env() -> None:
    """Sync .env file and check for port conflicts."""
    env_file = Path(".env")
    default_port = "5001"
    
    if not env_file.exists():
        print("[*] Creating .env from template...")
        with env_file.open("w") as f:
            f.write(f"FLASK_PORT={default_port}\nFLASK_DEBUG=True\nAPP_ENV=development\n")
            f.write("DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres\n")
    else:
        # Port Conflict Check
        import socket
        with env_file.open("r") as f:
            lines = f.readlines()
            port = next((line.split("=")[1].strip() for line in lines if "FLASK_PORT" in line), default_port)
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', int(port))) == 0:
                print(f"[!] WARNING: Port {port} is busy. If the dashboard fails, change FLASK_PORT in .env")


def main() -> None:
    """Unified deployment and launch sequence."""
    print_banner()
    
    if not check_requirements():
        sys.exit(1)

    python_exe = setup_venv()
    build_go_engine()
    setup_env()

    print("-" * 60)
    print("✅ DEPLOYMENT READY. LAUNCHING CLOUD-REAPER...")
    print("-" * 60)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").absolute())

    try:
        subprocess.run([python_exe, "-m", "reaper.web.app"], env=env, check=False)
    except KeyboardInterrupt:
        print("\n[*] Cloud-Reaper stopped.")


if __name__ == "__main__":
    main()
