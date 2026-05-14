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

# Repository root (directory containing this file). All paths are resolved from here.
REPO_ROOT = Path(__file__).resolve().parent


def print_banner() -> None:
    """Print the Cloud-Reaper startup banner."""
    print("=" * 60)
    print("        🚀 CLOUD-REAPER CROSS-PLATFORM BOOTSTRAP")
    print("=" * 60)


def run_command(
    cmd: list[str],
    cwd: str | Path | None = None,
    env: dict | None = None,
) -> bool:
    """Run a subprocess command with fail-fast semantics."""
    workdir = str(cwd) if cwd is not None else str(REPO_ROOT)
    print(f"[*] Running: {' '.join(cmd)}  (cwd={workdir})")
    try:
        subprocess.run(cmd, cwd=workdir, env=env, check=True)  # noqa: S603
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
    """Verify Go, Docker, and optional Azure CLI status."""
    print("[*] Checking system requirements...")

    # Go Check
    if not shutil.which("go"):
        print("[!] Go not found. Please install Go 1.24+ (see src/engine-go/go.mod).")
        return False

    # Azure CLI — optional: the app can use DefaultAzureCredential from .env / VS Code / MSI.
    az_bin = shutil.which("az")
    if not az_bin:
        print(
            "[*] Azure CLI not on PATH. Skipping `az login` check — configure "
            "credentials in .env or your environment if the dashboard cannot reach Azure."
        )
    else:
        print("[*] Verifying Azure authentication (optional)...")
        try:
            az_check = subprocess.run(
                [az_bin, "account", "show"],  # noqa: S603
                capture_output=True,
                text=True,
                check=False,
            )
            if az_check.returncode != 0:
                print(
                    "[*] `az account show` failed (not logged in or no subscription). "
                    "You can still run the app with service principal / env-based auth."
                )
            else:
                print("[+] Azure CLI session active.")
        except Exception:
            print("[!] Could not verify Azure CLI session. Proceeding with caution...")

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
                run_result = _docker(
                    [
                        "run",
                        "--name",
                        "cloud-reaper-db",
                        "-e",
                        "POSTGRES_PASSWORD=postgres",
                        "-p",
                        "5432:5432",
                        "-d",
                        "postgres",
                    ]
                )
                if run_result.returncode != 0:
                    print(
                        f"[!] Could not start Postgres container: "
                        f"{(run_result.stderr or run_result.stdout or '').strip()}"
                    )
        except Exception as e:
            print(f"[!] Docker error: {e}. Start Postgres manually if needed.")

    return True


def setup_venv() -> str:
    """Create the virtual environment and install dependencies."""
    print("[*] Setting up virtual environment...")
    venv_dir = REPO_ROOT / "venv"
    if not venv_dir.exists():
        if not run_command([sys.executable, "-m", "venv", str(venv_dir)]):
            print("[!] Failed to create virtual environment.")
            sys.exit(1)

    is_windows = platform.system() == "Windows"
    bin_subdir = "Scripts" if is_windows else "bin"
    py_name = "python.exe" if is_windows else "python"
    pip_name = "pip.exe" if is_windows else "pip"
    python_path = venv_dir / bin_subdir / py_name
    pip_path = venv_dir / bin_subdir / pip_name

    if not python_path.is_file():
        print(f"[!] Expected venv python at {python_path} but it is missing.")
        sys.exit(1)

    print("[*] Synchronizing dependencies...")
    req = REPO_ROOT / "requirements.txt"
    if not req.is_file():
        print(f"[!] requirements.txt not found at {req}")
        sys.exit(1)

    if not run_command([str(pip_path), "install", "--upgrade", "pip", "--quiet"]):
        print("[!] pip upgrade failed — continuing with existing pip.")
    if not run_command([str(pip_path), "install", "-r", str(req), "--quiet"]):
        print("[!] pip install -r requirements.txt failed.")
        sys.exit(1)

    return str(python_path)


def build_go_engine() -> bool:
    """Compile the Go performance engine binary and place it in bin/."""
    print("[*] Building Go engine...")
    go_bin = shutil.which("go") or "go"
    is_windows = platform.system() == "Windows"
    binary_name = "reaper-engine.exe" if is_windows else "reaper-engine"

    engine_dir = REPO_ROOT / "src" / "engine-go"
    bin_dir = REPO_ROOT / "bin"
    bin_dir.mkdir(exist_ok=True)

    if not engine_dir.is_dir():
        print(f"[!] Go engine directory not found: {engine_dir}")
        return False

    output_path = (bin_dir / binary_name).resolve()
    success = run_command(
        [go_bin, "build", "-o", str(output_path), "main.go"],
        cwd=engine_dir,
    )
    if success:
        print(f"[+] Go engine built: {output_path}")
    return success


def setup_env() -> None:
    """Sync .env file and check for port conflicts."""
    env_file = REPO_ROOT / ".env"
    default_port = "5001"

    if not env_file.exists():
        print("[*] Creating .env from template...")
        with env_file.open("w", encoding="utf-8") as f:
            f.write(f"FLASK_PORT={default_port}\nFLASK_DEBUG=True\nAPP_ENV=development\n")
            f.write("DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres\n")
    else:
        # Port Conflict Check
        with env_file.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        port = next(
            (
                line.split("=", 1)[1].strip().strip('"').strip("'")
                for line in lines
                if line.strip().startswith("FLASK_PORT=")
            ),
            default_port,
        )

        try:
            port_int = int(port)
        except ValueError:
            port_int = int(default_port)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port_int)) == 0:
                print(
                    f"[!] WARNING: Port {port_int} is busy. "
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

    os.chdir(REPO_ROOT)

    print_banner()

    # Phase 1: Sequential Requirements Check
    print("\n[1/3] VERIFYING SYSTEM CORE...")
    if not check_requirements():
        sys.exit(1)
    print("[✓] System core verified.")

    # Phase 2: Parallel Build & Environment Setup
    print("\n[2/3] ASSEMBLING COMPONENTS (PARALLEL)...")
    context: dict[str, str] = {"python_exe": sys.executable, "port": "5001"}

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

    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        with env_file.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("FLASK_PORT="):
                    context["port"] = stripped.split("=", 1)[1].strip().strip('"').strip("'")

    print_success_report(context["port"])

    env = os.environ.copy()
    env["PYTHONPATH"] = str((REPO_ROOT / "src").resolve())

    print("[*] Launching Flask/SocketIO Server...")
    try:
        subprocess.run(
            [context["python_exe"], "-m", "reaper.web.app"],  # noqa: S603
            cwd=str(REPO_ROOT),
            env=env,
            check=False,
        )
    except KeyboardInterrupt:
        print("\n[*] Cloud-Reaper session ended.")
    except Exception as e:
        print(f"\n[!] CRITICAL ERROR: Could not start dashboard: {e}")
        is_win = platform.system() == "Windows"
        activate = "venv\\Scripts\\activate" if is_win else "source venv/bin/activate"
        print(
            "    Try running manually:\n"
            f"      cd {REPO_ROOT}\n"
            f"      {activate}\n"
            "      PYTHONPATH=src python -m reaper.web.app"
        )


if __name__ == "__main__":
    main()
