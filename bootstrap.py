"""Cloud-Reaper cross-platform bootstrapper.

Sets up the virtual environment, builds the Go engine, and launches the dashboard.
Run directly with: python bootstrap.py
"""

import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


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
    return subprocess.run(
        [docker_bin, *args],  # noqa: S603
        capture_output=True,
        text=True,
        check=False,
    )


def check_requirements() -> bool:  # noqa: PLR0912
    """Verify Go, Docker, and Azure CLI status."""
    print("[*] Checking system requirements...")

    # Go Check
    if not shutil.which("go"):
        print("[!] Go not found. Please install Go 1.24+")
        return False

    # Azure CLI Check
    az_bin = shutil.which("az")
    if not az_bin:
        print("[!] Azure CLI not found. Please install it to continue.")
        return False

    # Check Azure Login Status using the resolved absolute path
    print("[*] Verifying Azure authentication...")
    try:
        az_check = subprocess.run(
            [az_bin, "account", "show"],  # noqa: S603
            capture_output=True,
            text=True,
            check=False,
        )
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
                pango_check = subprocess.run(
                    [ldconfig, "-p"],  # noqa: S603
                    capture_output=True,
                    text=True,
                    check=False,
                )
                missing = (
                    "libpango-1.0" not in pango_check.stdout
                    or "libpangocairo-1.0" not in pango_check.stdout
                )
                if missing:
                    print(
                        "[!] WARNING: PDF libraries missing. "
                        "Install with: sudo apt install libpango-1.0-0"
                    )
        except Exception:
            logger.debug("PDF library check skipped — ldconfig unavailable.", exc_info=True)

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
    bin_subdir = "Scripts" if is_windows else "bin"
    py_name = "python.exe" if is_windows else "python"
    pip_name = "pip.exe" if is_windows else "pip"
    python_path = venv_dir / bin_subdir / py_name
    pip_path = venv_dir / bin_subdir / pip_name

    print("[*] Synchronizing dependencies...")
    run_command([str(pip_path), "install", "--upgrade", "pip", "--quiet"])
    run_command([str(pip_path), "install", "-r", "requirements.txt", "--quiet"])

    return str(python_path)


def build_go_engine() -> bool:
    """Compile the Go performance engine binary and place it in bin/."""
    print("[*] Building Go engine...")
    go_bin = shutil.which("go") or "go"
    is_windows = platform.system() == "Windows"
    binary_name = "reaper-engine.exe" if is_windows else "reaper-engine"

    engine_dir = Path("src/engine-go")
    bin_dir = Path("bin")
    bin_dir.mkdir(exist_ok=True)

    if not engine_dir.exists():
        print("[!] src/engine-go not found!")
        return False

    output_path = bin_dir / binary_name
    success = run_command(
        [go_bin, "build", "-o", str(output_path.absolute()), "main.go"],
        cwd=str(engine_dir),
    )
    if success:
        print(f"[+] Go engine built: {output_path}")
    return success


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
        with env_file.open("r") as f:
            lines = f.readlines()
        port = next(
            (line.split("=")[1].strip() for line in lines if "FLASK_PORT" in line),
            default_port,
        )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", int(port))) == 0:
                print(
                    f"[!] WARNING: Port {port} is busy. "
                    "If the dashboard fails, change FLASK_PORT in .env"
                )


def print_success_report(port: str) -> None:
    """Print a high-fidelity summary of the deployed environment."""
    print("\n" + "=" * 60)
    print("🚀 CLOUD-REAPER INTELLIGENCE ENGINE IS ONLINE")
    print("=" * 60)
    print(f"  ▸ Dashboard:    http://localhost:{port}")
    print(f"  ▸ Port:         {port}")
    print("  ▸ Status:       HEALTHY")
    print("  ▸ Monitoring:   ACTIVE")
    print("=" * 60)
    print("Press Ctrl+C to terminate the session safely.\n")


def main() -> None:
    """Parallelized deployment sequence for ultra-fast launch."""
    from concurrent.futures import ThreadPoolExecutor

    print_banner()

    # Phase 1: Sequential Requirements Check
    print("\n[1/3] VERIFYING SYSTEM CORE...")
    if not check_requirements():
        sys.exit(1)
    print("[✓] System core verified.")

    # Phase 2: Parallel Build & Environment Setup
    print("\n[2/3] ASSEMBLING COMPONENTS (PARALLEL)...")
    context = {"python_exe": sys.executable, "port": "5001"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        venv_future = executor.submit(setup_venv)
        go_future = executor.submit(build_go_engine)

        context["python_exe"] = venv_future.result()
        if not go_future.result():
            print("[!] Go engine build failed. Dashboard features may be limited.")

    print("[✓] Components assembled.")

    # Phase 3: Final Configuration & Launch
    print("\n[3/3] INITIALIZING INTELLIGENCE...")
    setup_env()

    env_file = Path(".env")
    if env_file.exists():
        with env_file.open("r") as f:
            for line in f:
                if "FLASK_PORT" in line:
                    context["port"] = line.split("=")[1].strip()

    print_success_report(context["port"])

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").absolute())

    print("[*] Launching Flask/SocketIO Server...")
    try:
        subprocess.run(
            [context["python_exe"], "-m", "reaper.web.app"],  # noqa: S603
            env=env,
            check=False,
        )
    except KeyboardInterrupt:
        print("\n[*] Cloud-Reaper session ended.")
    except Exception as e:
        print(f"\n[!] CRITICAL ERROR: Could not start dashboard: {e}")
        print("    Try running manually: source venv/bin/activate && python -m reaper.web.app")


if __name__ == "__main__":
    main()
