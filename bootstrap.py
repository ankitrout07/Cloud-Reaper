import os
import sys
import subprocess
import platform
import shutil
import time
from pathlib import Path

def print_banner():
    print("=" * 60)
    print("        🚀 CLOUD-REAPER CROSS-PLATFORM BOOTSTRAP")
    print("=" * 60)

def run_command(cmd, cwd=None, env=None):
    print(f"[*] Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd, env=env, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] Error: {e}")
        return False

def check_requirements():
    print("[*] Checking system requirements...")
    
    # Check Go
    if not shutil.which("go"):
        print("[!] Go not found. Please install Go 1.24+")
        return False
    
    # Check Docker
    if shutil.which("docker"):
        print("[*] Docker found. Checking PostgreSQL container...")
        try:
            result = subprocess.run(["docker", "ps", "-a"], capture_output=True, text=True)
            if "cloud-reaper-db" not in result.stdout:
                print("[*] Starting PostgreSQL container...")
                subprocess.run([
                    "docker", "run", "--name", "cloud-reaper-db", 
                    "-e", "POSTGRES_PASSWORD=postgres", 
                    "-p", "5432:5432", "-d", "postgres"
                ], capture_output=True)
            else:
                subprocess.run(["docker", "start", "cloud-reaper-db"], capture_output=True)
        except Exception:
            print("[!] Could not interact with Docker. Proceeding without auto-db...")
    else:
        print("[!] Docker not found. Start PostgreSQL manually if needed.")
    
    return True

def setup_venv():
    print("[*] Setting up virtual environment...")
    if not os.path.exists("venv"):
        run_command([sys.executable, "-m", "venv", "venv"])
    
    is_windows = platform.system() == "Windows"
    pip_path = os.path.join("venv", "Scripts", "pip.exe") if is_windows else os.path.join("venv", "bin", "pip")
    python_path = os.path.join("venv", "Scripts", "python.exe") if is_windows else os.path.join("venv", "bin", "python")
    
    print("[*] Installing dependencies...")
    run_command([pip_path, "install", "--upgrade", "pip"])
    run_command([pip_path, "install", "-r", "requirements.txt", "-r", "requirements-dev.txt"])
    
    return python_path

def build_go_engine():
    print("[*] Building Go engine...")
    is_windows = platform.system() == "Windows"
    binary_name = "reaper-engine.exe" if is_windows else "reaper-engine"
    
    engine_dir = Path("src/engine-go")
    if not engine_dir.exists():
        print("[!] src/engine-go not found!")
        return False
        
    output_path = engine_dir / binary_name
    if run_command(["go", "build", "-o", binary_name, "main.go"], cwd=str(engine_dir)):
        print(f"[+] Go engine built: {output_path}")
        return True
    return False

def setup_env():
    if not os.path.exists(".env"):
        print("[*] Creating .env file from template...")
        with open(".env", "w") as f:
            f.write("# Cloud-Reaper Configuration\n")
            f.write("APP_ENV=development\n")
            f.write("FLASK_PORT=5001\n")
            f.write("FLASK_DEBUG=True\n")
            f.write("AZURE_SUBSCRIPTION_ID=your_subscription_id\n")
            f.write("DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres\n")
        print("[+] .env created. Defaulting to port 5001 to avoid macOS conflicts.")

def main():
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
    
    # Run the Flask app
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").absolute())
    
    try:
        subprocess.run([python_exe, "-m", "reaper.web.app"], env=env)
    except KeyboardInterrupt:
        print("\n[*] Stopping Cloud-Reaper...")

if __name__ == "__main__":
    main()
