import argparse
import sys
from pathlib import Path

# Set PYTHONPATH to include src directory
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reaper.engine.telemetry.metrics_cli import display_finops_performance_metrics


def main():
    parser = argparse.ArgumentParser(description="Cloud-Reaper FinOps CLI Engine")
    parser.add_argument(
        "--metrics", action="store_true", help="Display live performance FinOps analysis data"
    )
    parser.add_argument(
        "--provider",
        choices=["azure", "aws", "gcp"],
        help="Cloud provider to fetch metrics from (auto-detects if not specified)",
    )
    parser.add_argument(
        "--enhanced-pipeline",
        action="store_true",
        help="Use enhanced sequential FinOps pipeline with workload differentiation",
    )
    parser.add_argument(
        "--benchmark-migration",
        action="store_true",
        help="Run a benchmark comparing Python and Go-backed migration paths",
    )

    args, unknown = parser.parse_known_args()

    if args.metrics:
        display_finops_performance_metrics(cloud_provider=args.provider)
        sys.exit(0)

    if args.enhanced_pipeline:
        sys.argv.append("--enhanced-pipeline")  # Pass through to CLI

    if args.benchmark_migration:
        sys.argv.append("--benchmark-migration")  # Pass through to CLI

    # Import run_reaper only when needed to avoid Azure dependency issues
    from reaper.cli import run_reaper

    run_reaper()


if __name__ == "__main__":
    main()
