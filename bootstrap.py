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
    """Verify Go and Docker are present; start the PostgreSQL container if needed."""
    print("[*] Checking system requirements...")

    if not shutil.which("go"):
        print("[!] Go not found. Please install Go 1.24+")
        return False

    if shutil.which("docker"):
        print("[*] Docker found. Checking PostgreSQL container...")
        try:
            result = _docker(["ps", "-a"])
            if "cloud-reaper-db" not in result.stdout:
                print("[*] Starting PostgreSQL container...")
                _docker([
                    "run", "--name", "cloud-reaper-db",
                    "-e", "POSTGRES_PASSWORD=postgres",
                    "-p", "5432:5432", "-d", "postgres",
                ])
            else:
                _docker(["start", "cloud-reaper-db"])
        except Exception:
            print("[!] Could not interact with Docker. Proceeding without auto-db...")
    else:
        print("[!] Docker not found. Start PostgreSQL manually if needed.")

    return True


def setup_venv() -> str:
    """Create the virtual environment and install all dependencies."""
    print("[*] Setting up virtual environment...")

    venv_dir = Path("venv")
    if not venv_dir.exists():  # Fixes PTH110
        run_command([sys.executable, "-m", "venv", str(venv_dir)])

    is_windows = platform.system() == "Windows"
    if is_windows:
        pip_path = venv_dir / "Scripts" / "pip.exe"    # Fixes PTH118
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        pip_path = venv_dir / "bin" / "pip"             # Fixes PTH118
        python_path = venv_dir / "bin" / "python"

    print("[*] Installing dependencies...")
    run_command([str(pip_path), "install", "--upgrade", "pip"])
    run_command([
        str(pip_path), "install",
        "-r", "requirements.txt",
        "-r", "requirements-dev.txt",
    ])

    return str(python_path)


def build_go_engine() -> bool:
    """Compile the Go performance engine binary."""
    print("[*] Building Go engine...")
    go_bin = shutil.which("go") or "go"  # Fixes S607 via absolute path
    is_windows = platform.system() == "Windows"
    binary_name = "reaper-engine.exe" if is_windows else "reaper-engine"

    engine_dir = Path("src/engine-go")
    if not engine_dir.exists():
        print("[!] src/engine-go not found!")
        return False

    output_path = engine_dir / binary_name
    if run_command([go_bin, "build", "-o", binary_name, "main.go"], cwd=str(engine_dir)):
        print(f"[+] Go engine built: {output_path}")
        return True
    return False


def setup_env() -> None:
    """Create a default .env file if one does not exist."""
    env_file = Path(".env")
    if not env_file.exists():  # Fixes PTH110
        print("[*] Creating .env file from template...")
        with env_file.open("w") as f:  # Fixes PTH123
            f.write("# Cloud-Reaper Configuration\n")
            f.write("APP_ENV=development\n")
            f.write("FLASK_PORT=5001\n")
            f.write("FLASK_DEBUG=True\n")
            f.write("AZURE_SUBSCRIPTION_ID=your_subscription_id\n")
            f.write("DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres\n")
        print("[+] .env created. Defaulting to port 5001 to avoid macOS conflicts.")


def main() -> None:
    """Entry point: orchestrate the full bootstrap sequence."""
    print_banner()

    if not check_requirements():
        sys.exit(1)

    if not build_go_engine():
        print("[!] Failed to build Go engine. Proceeding anyway...")

    python_exe = setup_venv()
    setup_env()

    print("-" * 60)
    print("✅ SYSTEM READY. STARTING CLOUD-REAPER...")
    print("   Dashboard: http://localhost:5001")
    print("-" * 60)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").absolute())

    try:
        subprocess.run(  # noqa: S603
            [python_exe, "-m", "reaper.web.app"],
            env=env,
            check=False,
        )
    except KeyboardInterrupt:
        print("\n[*] Stopping Cloud-Reaper...")


if __name__ == "__main__":
    main()
