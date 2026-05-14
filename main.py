import sys
from pathlib import Path

# Set PYTHONPATH to include src directory
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reaper.cli import run_reaper  # noqa: E402

if __name__ == "__main__":
    run_reaper()
