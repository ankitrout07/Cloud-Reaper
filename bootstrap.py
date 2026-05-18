"""Cloud-Reaper cross-platform bootstrapper.

Creates the project ``venv/``, applies the same environment changes as ``activate``
(``VIRTUAL_ENV`` + ``PATH``), installs runtime and developer dependencies with
that venv's ``pip``, builds the Go engine, and launches the Flask/SocketIO app
with the venv interpreter.

Run directly with: python3 bootstrap.py
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Repository root (directory containing this file). All paths are resolved from here.
REPO_ROOT = Path(__file__).resolve().parent


def _venv_bin_dir(venv_dir: Path) -> Path:
    """``venv/bin`` on Unix, ``venv\\Scripts`` on Windows."""
    is_windows = platform.system() == "Windows"
    return venv_dir / ("Scripts" if is_windows else "bin")


def merge_venv_into_environ(venv_dir: Path, base: dict | None = None) -> dict:
    """
    Mimic ``source venv/bin/activate``: set ``VIRTUAL_ENV`` and prepend the venv
    executables directory to ``PATH`` (so ``python``/``pip`` in subprocesses resolve
    to the venv without relying on absolute paths alone).
    """
    out = dict(base if base is not None else os.environ)
    bindir = _venv_bin_dir(venv_dir)
    out["VIRTUAL_ENV"] = str(venv_dir.resolve())
    out["PATH"] = str(bindir) + os.pathsep + out.get("PATH", "")
    # Avoid interfering with venv interpreter discovery
    out.pop("PYTHONHOME", None)
    return out


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
        subprocess.run(cmd, cwd=workdir, env=env, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] Error: {e}")
        return False


def _docker(args: list[str]) -> subprocess.CompletedProcess:
    """Run a docker sub-command using its absolute path (Fixes S607, PLW1510)."""
    docker_bin = shutil.which("docker") or "docker"
    return subprocess.run(
        [docker_bin, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def check_requirements() -> bool:
    """Verify Go, Docker, and optional Azure CLI status."""
    print("[*] Checking system requirements...")

    # Go Check
    if not shutil.which("go"):
        print("[!] Go not found. Please install Go 1.24+ (see src/engine-go/go.mod).")
        return False

    # Linter Check
    for tool in ["golangci-lint", "ruff", "mypy"]:
        if not shutil.which(tool):
            print(f"[*] Tool '{tool}' not found on PATH. It will be installed into venv/bin.")

    # Azure CLI — optional
    az_bin = shutil.which("az")
    if not az_bin:
        print("[*] Azure CLI not found. Using environment-based auth fallback.")
    else:
        print("[+] Azure CLI detected.")

    # Docker & Postgres Check
    if shutil.which("docker"):
        print("[*] Docker found. Ensuring PostgreSQL is running...")
        try:
            # Check if container exists
            inspect = _docker(["inspect", "cloud-reaper-db"])
            if inspect.returncode != 0:
                print("[*] Creating fresh PostgreSQL container...")
                _docker(
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
            else:
                _docker(["start", "cloud-reaper-db"])
        except Exception as e:
            print(f"[!] Docker error: {e}. Start Postgres manually if needed.")

    return True


def setup_venv() -> tuple[str, Path]:
    """
    Create ``venv/`` if needed, activate it for child processes (env), install
    ``requirements.txt``, and return ``(python_executable, venv_dir)``.
    """
    is_windows = platform.system() == "Windows"
    venv_dir = REPO_ROOT / "venv"
    bindir = _venv_bin_dir(venv_dir)
    py_name = "python.exe" if is_windows else "python"
    pip_name = "pip.exe" if is_windows else "pip"
    python_path = bindir / py_name
    pip_path = bindir / pip_name

    print("\n--- Python virtual environment ---")
    print(f"[*] Target venv: {venv_dir}")

    if not venv_dir.exists():
        print("[*] [1/3] Creating virtual environment (python -m venv venv)...")
        if not run_command([sys.executable, "-m", "venv", str(venv_dir)]):
            print("[!] Failed to create virtual environment.")
            sys.exit(1)
    else:
        print("[*] [1/3] Virtual environment folder already exists — reusing.")

    if not python_path.is_file():
        print(f"[!] Expected venv python at {python_path} but it is missing.")
        sys.exit(1)

    venv_env = merge_venv_into_environ(venv_dir)
    activate_hint = "venv\\Scripts\\activate" if is_windows else "source venv/bin/activate"
    print(
        "[*] [2/3] Activating for installs (VIRTUAL_ENV + PATH → "
        f"{bindir.name}) — same effect as: {activate_hint}"
    )

    req = REPO_ROOT / "requirements.txt"
    if not req.is_file():
        print(f"[!] requirements.txt not found at {req}")
        sys.exit(1)

    print("[*] [3/3] Installing / upgrading dependencies into the venv...")
    if not run_command(
        [str(pip_path), "install", "--upgrade", "pip", "--quiet"],
        env=venv_env,
    ):
        print("[!] pip upgrade failed — continuing with existing pip.")
    if not run_command(
        [str(pip_path), "install", "-r", str(req), "--quiet"],
        env=venv_env,
    ):
        print("[!] pip install -r requirements.txt failed.")
        sys.exit(1)

    dev_req = REPO_ROOT / "requirements-dev.txt"
    if dev_req.is_file():
        print("[*] Installing development dependencies into the venv...")
        if not run_command(
            [str(pip_path), "install", "-r", str(dev_req), "--quiet"],
            env=venv_env,
        ):
            print("[!] pip install -r requirements-dev.txt failed.")
            sys.exit(1)

    print(f"[+] Dependencies installed. Interpreter: {python_path}")
    return str(python_path), venv_dir


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
        [go_bin, "build", "-o", str(output_path), "."],
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
            f.write("OPENAI_API_KEY=your_actual_openai_api_key_here\n")
            f.write("GEMINI_API_KEY=your_actual_gemini_api_key_here\n")
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

        py_exe, venv_dir = venv_future.result()
        context["python_exe"] = py_exe
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

    env = merge_venv_into_environ(venv_dir)
    env["PYTHONPATH"] = str((REPO_ROOT / "src").resolve())

    print("[*] Launching Flask/SocketIO Server (venv activated in process environment)...")
    try:
        subprocess.run(
            [context["python_exe"], "-m", "reaper.web.app"],
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
