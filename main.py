import sys
import os

# Set PYTHONPATH to include src directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from reaper.cli import run_reaper

if __name__ == "__main__":
    run_reaper()
