import sys
import argparse
from pathlib import Path

# Set PYTHONPATH to include src directory
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reaper.engine.metrics_cli import display_finops_performance_metrics
from reaper.cli import run_reaper

def main():
    parser = argparse.ArgumentParser(description="Cloud-Reaper FinOps CLI Engine")
    parser.add_argument('--metrics', action='store_true', help="Display live performance FinOps analysis data")
    
    args, unknown = parser.parse_known_args()
    
    if args.metrics:
        display_finops_performance_metrics()
        sys.exit(0)
        
    run_reaper()

if __name__ == "__main__":
    main()
