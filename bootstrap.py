"""Cloud-Reaper cross-platform bootstrapper — Ubuntu CLI edition.

Provides a rich argparse CLI with subcommands:

  python3 bootstrap.py                  # full boot (install + build + launch web)
  python3 bootstrap.py run              # same as above (explicit)
  python3 bootstrap.py install          # create venv & install all Python deps
  python3 bootstrap.py build            # build Go engine binary
  python3 bootstrap.py check            # verify system prerequisites
  python3 bootstrap.py scan             # run the Azure FinOps CLI scan
  python3 bootstrap.py metrics          # display live FinOps performance metrics
  python3 bootstrap.py web              # launch the FastAPI ASGI dashboard
  python3 bootstrap.py clean            # remove build artefacts & caches
  python3 bootstrap.py pr-simulation    # run a PR cost delta simulation

Run  python3 bootstrap.py --help  for the full option reference.
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI colour palette (Ubuntu terminal safe)
# ---------------------------------------------------------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"


def c(text: str, colour: str) -> str:
    """Wrap *text* in an ANSI colour code (no-op on Windows without ANSI support)."""
    if platform.system() == "Windows":
        return text
    return f"{colour}{text}{RESET}"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _venv_bin_dir(venv_dir: Path) -> Path:
    """``venv/bin`` on Unix, ``venv\\Scripts`` on Windows."""
    return venv_dir / ("Scripts" if platform.system() == "Windows" else "bin")


def merge_venv_into_environ(venv_dir: Path, base: dict | None = None) -> dict:
    """
    Mimic ``source venv/bin/activate``: set ``VIRTUAL_ENV`` and prepend the venv
    executables directory to ``PATH`` so that ``python``/``pip`` in child processes
    resolve to the venv without relying on absolute paths alone.
    """
    out = dict(base if base is not None else os.environ)
    bindir = _venv_bin_dir(venv_dir)
    out["VIRTUAL_ENV"] = str(venv_dir.resolve())
    out["PATH"] = str(bindir) + os.pathsep + out.get("PATH", "")
    out.pop("PYTHONHOME", None)
    return out


def _docker(args: list[str]) -> subprocess.CompletedProcess:
    """Run a docker sub-command using its absolute path."""
    docker_bin = shutil.which("docker") or "docker"
    return subprocess.run(
        [docker_bin, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def run_cmd(
    cmd: list[str],
    cwd: str | Path | None = None,
    env: dict | None = None,
    *,
    quiet: bool = False,
) -> bool:
    """Run a subprocess command with fail-fast semantics."""
    workdir = str(cwd) if cwd is not None else str(REPO_ROOT)
    if not quiet:
        print(c(f"  › {' '.join(cmd)}", DIM))
    try:
        subprocess.run(cmd, cwd=workdir, env=env, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(c(f"[!] Command failed (exit {exc.returncode}): {' '.join(cmd)}", RED))
        return False


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def print_banner() -> None:
    width = 62
    print()
    print(c("=" * width, CYAN))
    print(c("  ☁️  CLOUD-REAPER  ·  Ubuntu CLI Bootstrap", BOLD + CYAN))
    print(c("=" * width, CYAN))
    print()


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Verify all system prerequisites and print a status table."""
    print(c("\n[1/1] System prerequisite check", BOLD))

    ok = True
    checks = {
        "python3": ("Python 3.12+", True),
        "go": ("Go 1.24+", True),
        "docker": ("Docker", False),
        "az": ("Azure CLI", False),
        "git": ("Git", False),
    }

    if platform.system() == "Linux":
        checks["pkg-config"] = ("pkg-config", True)

    for binary, (label, required) in checks.items():
        found = shutil.which(binary)
        if found:
            print(f"  {c('✔', GREEN)}  {label:<18} {c(found, DIM)}")
        elif required:
            print(f"  {c('✗', RED)}  {label:<18} {c('NOT FOUND — required', RED)}")
            ok = False
        else:
            print(f"  {c('⚠', YELLOW)}  {label:<18} {c('not found (optional)', YELLOW)}")

    # Docker + PostgreSQL status
    if shutil.which("docker"):
        result = _docker(["inspect", "--format", "{{.State.Status}}", "cloud-reaper-db"])
        db_status = result.stdout.strip() if result.returncode == 0 else "not created"
        colour = GREEN if db_status == "running" else YELLOW
        print(f"  {c('ℹ', CYAN)}  {'PostgreSQL DB':<18} {c(db_status, colour)}")

    # Port check
    port = _read_port_from_env()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            busy = s.connect_ex(("127.0.0.1", int(port))) == 0
        port_colour = RED if busy else GREEN
        port_label = (
            f"port {port} BUSY — change FLASK_PORT in .env" if busy else f"port {port} free"
        )
        print(f"  {c('ℹ', CYAN)}  {'Dashboard port':<18} {c(port_label, port_colour)}")
    except ValueError:
        pass

    if ok:
        print(c("\n[✔] All required prerequisites satisfied.\n", GREEN))
        return 0

    print(c("\n[✗] One or more required tools are missing. Install them and retry.\n", RED))
    print("    Ubuntu quick-install hints:")
    print(
        "      sudo apt-get update && sudo apt-get install -y golang-go docker.io pkg-config libwebkit2gtk-4.1-dev libgtk-3-dev"
    )
    print("      curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash")
    return 1


def cmd_install(args: argparse.Namespace) -> int:
    """Create venv and install Python runtime + dev dependencies."""
    print(c("\n[install] Setting up Python virtual environment\n", BOLD))

    venv_dir = REPO_ROOT / "venv"
    bindir = _venv_bin_dir(venv_dir)
    pip_path = bindir / "pip"

    # --- Create venv ---
    if not venv_dir.exists():
        print(c("  Creating virtual environment …", CYAN))
        if not run_cmd([sys.executable, "-m", "venv", str(venv_dir)]):
            print(c("[!] Failed to create virtual environment.", RED))
            return 1
    else:
        print(c("  Virtual environment already exists — reusing.", DIM))

    venv_env = merge_venv_into_environ(venv_dir)

    # --- Upgrade pip ---
    print(c("  Upgrading pip …", CYAN))
    run_cmd([str(pip_path), "install", "--upgrade", "pip", "--quiet"], env=venv_env)

    # --- Runtime deps ---
    req = REPO_ROOT / "requirements.txt"
    if not req.is_file():
        print(c(f"[!] requirements.txt not found at {req}", RED))
        return 1
    print(c("  Installing runtime dependencies (requirements.txt) …", CYAN))
    if not run_cmd([str(pip_path), "install", "-r", str(req), "--quiet"], env=venv_env):
        print(c("[!] pip install -r requirements.txt failed.", RED))
        return 1

    # --- Dev deps ---
    dev_req = REPO_ROOT / "requirements-dev.txt"
    if dev_req.is_file() and not getattr(args, "no_dev", False):
        print(c("  Installing dev dependencies (requirements-dev.txt) …", CYAN))
        if not run_cmd([str(pip_path), "install", "-r", str(dev_req), "--quiet"], env=venv_env):
            print(c("[!] pip install -r requirements-dev.txt failed.", RED))
            return 1

    # --- Go module download ---
    if shutil.which("go"):
        engine_dir = REPO_ROOT / "src" / "engine-go"
        if engine_dir.is_dir():
            print(c("  Downloading Go modules …", CYAN))
            run_cmd(["go", "mod", "download"], cwd=engine_dir)

    print(c("\n[✔] Install complete.\n", GREEN))
    return 0


def cmd_build(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Compile the Go performance engine binary into bin/."""
    print(c("\n[build] Compiling Go engine\n", BOLD))

    go_bin = shutil.which("go")
    if not go_bin:
        print(c("[!] Go not found. Install Go 1.24+ first.", RED))
        print("    sudo apt-get install -y golang-go")
        print("    # or follow https://golang.org/dl/")
        return 1

    # Create pkg-config shim for webkit2gtk-4.0 -> webkit2gtk-4.1 if needed
    if platform.system() == "Linux":
        pkg_config_path = "/usr/lib/x86_64-linux-gnu/pkgconfig"
        webkit_4_0 = os.path.join(pkg_config_path, "webkit2gtk-4.0.pc")
        webkit_4_1 = os.path.join(pkg_config_path, "webkit2gtk-4.1.pc")

        if os.path.exists(webkit_4_1) and not os.path.exists(webkit_4_0):
            print(c("  Creating pkg-config shim for webkit2gtk-4.0 → webkit2gtk-4.1", CYAN))
            try:
                # Try creating symlink (requires sudo)
                subprocess.run(
                    ["sudo", "ln", "-s", webkit_4_1, webkit_4_0], check=False, capture_output=True
                )
                if os.path.exists(webkit_4_0):
                    print(c("  ✓ pkg-config shim created", GREEN))
            except Exception:
                # If sudo fails, try setting PKG_CONFIG_PATH environment variable
                print(c("  ! Could not create shim (requires sudo), using workaround", YELLOW))
                os.environ["PKG_CONFIG_PATH"] = pkg_config_path

    engine_dir = REPO_ROOT / "src" / "engine-go"
    bin_dir = REPO_ROOT / "bin"
    bin_dir.mkdir(exist_ok=True)
    binary_name = "reaper-engine.exe" if platform.system() == "Windows" else "reaper-engine"
    output_path = (bin_dir / binary_name).resolve()

    if not engine_dir.is_dir():
        print(c(f"[!] Go engine directory not found: {engine_dir}", RED))
        return 1

    print(c(f"  Building → {output_path}", CYAN))
    build_env = os.environ.copy()
    # Add pkg-config path to environment if we set it earlier
    if os.environ.get("PKG_CONFIG_PATH"):
        build_env["PKG_CONFIG_PATH"] = os.environ["PKG_CONFIG_PATH"]

    if not run_cmd(
        [go_bin, "build", "-tags", "cli", "-o", str(output_path), "."],
        cwd=engine_dir,
        env=build_env,
    ):
        print(c("[!] Go engine build failed. Dashboard features may be limited.", YELLOW))
        return 0  # Return 0 to continue since this is not critical

    # Ensure binary is executable on Unix
    if platform.system() != "Windows":
        output_path.chmod(0o755)

    print(c(f"\n[✔] Go engine built: {output_path}\n", GREEN))
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Remove build artefacts, caches, and optionally the venv."""
    print(c("\n[clean] Removing build artefacts\n", BOLD))

    targets = [
        REPO_ROOT / "bin",
        REPO_ROOT / "__pycache__",
        REPO_ROOT / ".pytest_cache",
        REPO_ROOT / ".ruff_cache",
        REPO_ROOT / ".mypy_cache",
    ]

    for t in targets:
        if t.exists():
            print(c(f"  Removing {t.relative_to(REPO_ROOT)}", CYAN))
            shutil.rmtree(t, ignore_errors=True)

    # Recursively remove __pycache__ under src/
    for p in (REPO_ROOT / "src").rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)

    if getattr(args, "venv", False):
        venv_dir = REPO_ROOT / "venv"
        if venv_dir.exists():
            print(c("  Removing venv/", YELLOW))
            shutil.rmtree(venv_dir)

    print(c("\n[✔] Clean complete.\n", GREEN))
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    """Run the Azure FinOps CLI scan inside the venv."""
    print(c("\n[scan] Launching Azure FinOps scan\n", BOLD))
    venv_dir, py_exe = _require_venv()
    if py_exe is None:
        return 1

    env = merge_venv_into_environ(venv_dir)
    env["PYTHONPATH"] = str((REPO_ROOT / "src").resolve())

    extra = []
    if getattr(args, "pr_simulation", False):
        extra = ["--pr-simulation"]
    if getattr(args, "metrics_flag", False):
        extra = ["--metrics"]

    try:
        result = subprocess.run(
            [py_exe, str(REPO_ROOT / "main.py"), *extra],
            cwd=str(REPO_ROOT),
            env=env,
            check=False,
        )
        return result.returncode
    except KeyboardInterrupt:
        print(c("\n[*] Scan interrupted.", YELLOW))
        return 0


def cmd_metrics(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Display live FinOps performance metrics (no cloud credentials needed)."""
    print(c("\n[metrics] Live FinOps performance metrics\n", BOLD))
    venv_dir, py_exe = _require_venv()
    if py_exe is None:
        return 1

    env = merge_venv_into_environ(venv_dir)
    env["PYTHONPATH"] = str((REPO_ROOT / "src").resolve())

    try:
        result = subprocess.run(
            [py_exe, str(REPO_ROOT / "main.py"), "--metrics"],
            cwd=str(REPO_ROOT),
            env=env,
            check=False,
        )
        return result.returncode
    except KeyboardInterrupt:
        return 0


def _init_database() -> bool:
    """Initialize the SQLite database with schema."""
    print(c("  Initializing database …", CYAN))
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "reaper.db"

    try:
        # Use venv Python for database initialization to ensure all dependencies are available
        venv_dir, py_exe = _require_venv()
        if py_exe is None:
            print(c("  Virtual environment not found, skipping database initialization", YELLOW))
            return True

        env = merge_venv_into_environ(venv_dir)
        env["PYTHONPATH"] = str((REPO_ROOT / "src").resolve())

        # Force SQLite for initialization to avoid PostgreSQL dependency issues
        env["DATABASE_URL"] = f"sqlite:///{db_path}"

        # Use the venv Python to run database initialization
        result = subprocess.run(
            [py_exe, "-c", "from reaper.engine.models.resources import init_db; init_db()"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            if db_path.exists():
                print(c(f"  Database ready: {db_path}", GREEN))
            else:
                print(c(f"  Database created: {db_path}", GREEN))
            return True
        print(c(f"  Database initialization warning: {result.stderr}", YELLOW))
        # Don't fail - SQLite will auto-create on first use
        return True
    except Exception as e:
        print(c(f"  Database initialization: {e}", YELLOW))
        # Don't fail - SQLite will auto-create on first use
        return True


def cmd_web(args: argparse.Namespace) -> int:
    """Launch the FastAPI ASGI dashboard and Go HTTP bridge."""
    print(c("\n[web] Starting FastAPI ASGI dashboard\n", BOLD))

    # Setup env file (safe to call multiple times)
    _setup_env_file()

    venv_dir, py_exe = _require_venv()
    if py_exe is None:
        return 1

    port = getattr(args, "port", None) or _read_port_from_env()
    env = merge_venv_into_environ(venv_dir)
    env["PYTHONPATH"] = str((REPO_ROOT / "src").resolve())
    env["FLASK_PORT"] = str(port)

    # Use SQLite by default for local development (override any PostgreSQL URL from .env)
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "reaper.db"
    env["DATABASE_URL"] = f"sqlite:///{db_path}"

    # Initialize database
    _init_database()

    _print_success_report(str(port))

    go_proc = None
    try:
        # Start Go bridge server first
        go_bin = (
            REPO_ROOT
            / "bin"
            / ("reaper-engine.exe" if platform.system() == "Windows" else "reaper-engine")
        )
        if go_bin.exists():
            print(c("  Starting Go HTTP bridge (port 7070) …", CYAN))
            go_proc = subprocess.Popen(
                [str(go_bin), "--mode", "serve", "--port", "7070"],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.DEVNULL,  # Keep Uvicorn logs clean
                stderr=subprocess.DEVNULL,
            )
        else:
            print(
                c("  [⚠] Go engine binary not found in bin/. Bridge features may fallback.", YELLOW)
            )

        subprocess.run(
            [
                py_exe,
                "-m",
                "uvicorn",
                "reaper.web.app_async:socket_app",
                "--host",
                env.get("FLASK_HOST", "0.0.0.0"),
                "--port",
                str(port),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            check=False,
        )
        return 0
    except KeyboardInterrupt:
        print(c("\n[*] Cloud-Reaper session ended gracefully.", CYAN))
        return 0
    except Exception as exc:
        print(c(f"\n[!] CRITICAL: Could not start dashboard: {exc}", RED))
        print("\n  Try manually:")
        print(f"    cd {REPO_ROOT}")
        print("    source venv/bin/activate")
        print("    PYTHONPATH=src python -m uvicorn reaper.web.app_async:socket_app")
        return 1
    finally:
        if go_proc:
            go_proc.terminate()
            go_proc.wait()


def cmd_pr_simulation(args: argparse.Namespace) -> int:
    """Run a PR cost-delta simulation report."""
    print(c("\n[pr-simulation] Pull-Request Cost Simulation\n", BOLD))
    venv_dir, py_exe = _require_venv()
    if py_exe is None:
        return 1

    env = merge_venv_into_environ(venv_dir)
    env["PYTHONPATH"] = str((REPO_ROOT / "src").resolve())

    extra = ["--pr-simulation"]
    if getattr(args, "file", None):
        extra.append(args.file)

    result = subprocess.run(
        [py_exe, str(REPO_ROOT / "main.py"), *extra],
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
    )
    return result.returncode


def cmd_run(args: argparse.Namespace) -> int:
    """Full boot sequence: check → install → build → web (parallelised)."""
    print_banner()

    # Phase 1 — Requirements
    print(c("[1/4] VERIFYING SYSTEM CORE …", BOLD + CYAN))
    if cmd_check(args) != 0:
        sys.exit(1)

    # Phase 2 — Parallel install + build
    print(c("[2/4] ASSEMBLING COMPONENTS (parallel) …", BOLD + CYAN))
    context: dict[str, str] = {"port": _read_port_from_env()}

    with ThreadPoolExecutor(max_workers=2) as executor:
        install_future = executor.submit(cmd_install, args)
        build_future = executor.submit(cmd_build, args)

        if install_future.result() != 0:
            print(c("[!] Install step failed.", RED))
            sys.exit(1)
        if build_future.result() != 0:
            print(c("[!] Go engine build failed. Dashboard features may be limited.", YELLOW))

    print(c("[✔] Components assembled.\n", GREEN))

    # Phase 3 — Setup environment
    print(c("[3/4] CONFIGURING ENVIRONMENT …", BOLD + CYAN))
    _setup_env_file()
    context["port"] = _read_port_from_env()
    if getattr(args, "port", None):
        context["port"] = str(args.port)

    # Initialize database
    _init_database()
    print(c("[✔] Environment configured.\n", GREEN))

    # Phase 4 — Launch web dashboard
    print(c("[4/4] INITIALIZING INTELLIGENCE …", BOLD + CYAN))

    # Inject --port into args so cmd_web can read it
    args.port = context["port"]
    return cmd_web(args)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _require_venv() -> tuple[Path, str | None]:
    """Return (venv_dir, python_exe_str).  If venv is missing, print hint and return None."""
    venv_dir = REPO_ROOT / "venv"
    python_exe = str(_venv_bin_dir(venv_dir) / "python")

    if not venv_dir.exists() or not Path(python_exe).is_file():
        print(c("[!] Virtual environment not found. Run first:", YELLOW))
        print(c("      python3 bootstrap.py install", CYAN))
        return venv_dir, None

    return venv_dir, python_exe


def _read_port_from_env() -> str:
    """Read FLASK_PORT from .env or return default 5001."""
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        with env_file.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("FLASK_PORT="):
                    return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return "5001"


def _setup_env_file() -> None:
    """Create a default .env if one doesn't exist; patch missing keys."""
    env_file = REPO_ROOT / ".env"
    default_port = "5001"

    if not env_file.exists():
        print(c("  Creating .env from defaults …", CYAN))
        with env_file.open("w", encoding="utf-8") as f:
            f.write(
                f"# Cloud-Reaper environment — auto-generated by bootstrap.py\n"
                f"APP_ENV=development\n"
                f"FLASK_PORT={default_port}\n"
                f"FLASK_HOST=0.0.0.0\n"
                f"FLASK_DEBUG=True\n"
                f"\n"
                f"# Database: Uses SQLite by default (no setup needed)\n"
                f"# To use PostgreSQL instead, set DATABASE_URL=postgresql://user:pass@localhost:5432/reaper\n"
                f"# DATABASE_URL=sqlite:///./data/reaper.db\n"
                f"\n"
                f"# Optional: Azure Credentials (for cloud scanning features)\n"
                f"# AZURE_SUBSCRIPTION_ID=your_subscription_id\n"
                f"# AZURE_TENANT_ID=your_tenant_id\n"
                f"# AZURE_CLIENT_ID=your_client_id\n"
                f"# AZURE_CLIENT_SECRET=your_client_secret\n"
                f"\n"
                f"# Optional: AI/GenAI API Keys (for Copilot & AI Architect)\n"
                f"# OPENAI_API_KEY=your_openai_api_key\n"
                f"# GEMINI_API_KEY=your_gemini_api_key\n"
                f"\n"
                f"# Optional: Notifications\n"
                f"# DISCORD_WEBHOOK_URL=your_discord_webhook\n"
            )
        print(c(f"  .env created at {env_file}", GREEN))
        print(c("  → Fill in optional secrets as needed for full functionality", YELLOW))
        return

    # Patch: append any missing keys
    with env_file.open("r", encoding="utf-8") as f:
        content = f.read()

    additions: list[str] = []
    for key, default in [
        ("FLASK_HOST", "0.0.0.0"),
    ]:
        if f"{key}=" not in content:
            additions.append(f"{key}={default}")

    if additions:
        with env_file.open("a", encoding="utf-8") as f:
            f.write("\n# Added by bootstrap.py\n")
            f.write("\n".join(additions) + "\n")
        print(c(f"  Patched .env with {len(additions)} missing key(s).", CYAN))

    # Port busy check
    port = _read_port_from_env()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", int(port))) == 0:
                print(
                    c(
                        f"  [⚠] Port {port} is in use. Change FLASK_PORT in .env if the dashboard fails.",
                        YELLOW,
                    )
                )
    except ValueError:
        pass


def _print_success_report(port: str) -> None:
    width = 62
    print()
    print(c("=" * width, GREEN))
    print(c("  🚀  CLOUD-REAPER INTELLIGENCE ENGINE IS ONLINE", BOLD + GREEN))
    print(c("=" * width, GREEN))
    print(f"  {c('▸ Dashboard:', BOLD)}  http://localhost:{port}")
    print(f"  {c('▸ Port:     ', BOLD)}  {port}")
    print(f"  {c('▸ Status:   ', BOLD)}  {c('HEALTHY', GREEN)}")
    print(f"  {c('▸ Engine:   ', BOLD)}  FastAPI + Uvicorn + Go HTTP Bridge")
    print(c("=" * width, GREEN))
    print(c("  Press Ctrl+C to terminate the session safely.", DIM))
    print()


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap.py",
        description=c("Cloud-Reaper — Ubuntu CLI Bootstrap", BOLD),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python3 bootstrap.py                    # full boot (default)
  python3 bootstrap.py run                # same as above
  python3 bootstrap.py install            # venv + pip deps only
  python3 bootstrap.py install --no-dev   # skip dev deps
  python3 bootstrap.py build              # compile Go engine
  python3 bootstrap.py check              # prerequisite check
  python3 bootstrap.py scan               # Azure FinOps scan
  python3 bootstrap.py metrics            # live FinOps metrics
  python3 bootstrap.py web                # start dashboard
  python3 bootstrap.py web --port 8080    # dashboard on custom port
  python3 bootstrap.py pr-simulation      # PR cost simulation
  python3 bootstrap.py clean              # remove build artefacts
  python3 bootstrap.py clean --venv       # also remove venv/
""",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- run (default) ----
    p_run = sub.add_parser("run", help="Full boot sequence: install + build + web (default)")
    p_run.add_argument(
        "--port", type=int, help="Override dashboard port (default: FLASK_PORT in .env or 5001)"
    )
    p_run.add_argument("--no-dev", dest="no_dev", action="store_true", help="Skip dev dependencies")
    p_run.set_defaults(func=cmd_run)

    # ---- install ----
    p_install = sub.add_parser("install", help="Create venv & install Python dependencies")
    p_install.add_argument(
        "--no-dev", dest="no_dev", action="store_true", help="Skip requirements-dev.txt"
    )
    p_install.set_defaults(func=cmd_install)

    # ---- build ----
    p_build = sub.add_parser("build", help="Compile the Go performance engine (outputs to bin/)")
    p_build.set_defaults(func=cmd_build)

    # ---- check ----
    p_check = sub.add_parser(
        "check", help="Verify system prerequisites (Go, Docker, Azure CLI, port …)"
    )
    p_check.set_defaults(func=cmd_check)

    # ---- scan ----
    p_scan = sub.add_parser("scan", help="Run the Azure FinOps CLI scan")
    p_scan.add_argument(
        "--pr-simulation",
        dest="pr_simulation",
        action="store_true",
        help="Run PR cost-delta simulation instead",
    )
    p_scan.add_argument(
        "--metrics",
        dest="metrics_flag",
        action="store_true",
        help="Show live FinOps performance metrics instead",
    )
    p_scan.set_defaults(func=cmd_scan)

    # ---- metrics ----
    p_metrics = sub.add_parser("metrics", help="Display live FinOps performance metrics")
    p_metrics.set_defaults(func=cmd_metrics)

    # ---- web ----
    p_web = sub.add_parser("web", help="Launch the FastAPI ASGI dashboard")
    p_web.add_argument("--port", type=int, help="Dashboard port (overrides .env FLASK_PORT)")
    p_web.set_defaults(func=cmd_web)

    # ---- pr-simulation ----
    p_pr = sub.add_parser("pr-simulation", help="Run a PR cost-delta simulation")
    p_pr.add_argument("file", nargs="?", default=None, help="Optional path to a dry-run plan file")
    p_pr.set_defaults(func=cmd_pr_simulation)

    # ---- clean ----
    p_clean = sub.add_parser("clean", help="Remove bin/, caches, __pycache__ trees")
    p_clean.add_argument("--venv", action="store_true", help="Also delete the venv/ directory")
    p_clean.set_defaults(func=cmd_clean)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    os.chdir(REPO_ROOT)
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        # No subcommand → full boot (same as `run`)
        args.command = "run"
        args.port = None
        args.no_dev = False
        args.func = cmd_run

    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
