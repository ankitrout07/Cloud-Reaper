import argparse
import sys
from pathlib import Path

# Set PYTHONPATH to include src directory
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reaper.cli import run_reaper
from reaper.engine.telemetry.metrics_cli import display_finops_performance_metrics


def main():
    parser = argparse.ArgumentParser(description="Cloud-Reaper FinOps CLI Engine")
    parser.add_argument(
        "--metrics", action="store_true", help="Display live performance FinOps analysis data"
    )
    parser.add_argument(
        "--provider", 
        choices=["azure", "aws", "gcp"],
        help="Cloud provider to fetch metrics from (auto-detects if not specified)"
    )
    parser.add_argument(
        "--enhanced-pipeline",
        action="store_true",
        help="Use enhanced sequential FinOps pipeline with workload differentiation",
    )

    args, unknown = parser.parse_known_args()

    if args.metrics:
        display_finops_performance_metrics(cloud_provider=args.provider)
        sys.exit(0)

    if args.enhanced_pipeline:
        sys.argv.append("--enhanced-pipeline")  # Pass through to CLI

    run_reaper()


if __name__ == "__main__":
    main()
