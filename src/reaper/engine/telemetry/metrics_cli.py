# src/reaper/engine/metrics_cli.py

import logging
import os

# Terminal ANSI Color Escape Codes for clean high-contrast Ubuntu formatting
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
BOLD = "\033[1m"

logger = logging.getLogger("reaper.metrics_cli")


def display_finops_performance_metrics(cloud_provider: str | None = None):
    """
    Prints action-oriented FinOps performance metrics with clear optimization descriptions.
    Requires real data from cloud providers - no simulated data.

    Args:
        cloud_provider: Cloud provider to fetch metrics from ('azure', 'aws', 'gcp').
                       If None, attempts to auto-detect from environment.
    """
    print(f"\n{BOLD}{CYAN}=== CLOUD-REAPER LIVE PERFORMANCE FINOPS METRICS ==={RESET}\n")

    # Auto-detect provider if not specified
    if cloud_provider is None:
        if os.getenv("AZURE_SUBSCRIPTION_ID"):
            cloud_provider = "azure"
        elif os.getenv("AWS_DEFAULT_REGION"):
            cloud_provider = "aws"
        elif os.getenv("GOOGLE_CLOUD_PROJECT"):
            cloud_provider = "gcp"

    if not cloud_provider:
        print(f"{RED}✗ Error: No cloud provider configured.{RESET}")
        print(f"{YELLOW}Please set cloud credentials in your environment:{RESET}")
        print(f"  - Azure: Set AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET")
        print(f"  - AWS: Set AWS_DEFAULT_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        print(f"  - GCP: Set GOOGLE_CLOUD_PROJECT, GOOGLE_APPLICATION_CREDENTIALS")
        return

    compute_metrics = {}
    storage_metrics = {}
    network_metrics = {}

    if cloud_provider == "azure":
        try:
            from reaper.collectors.providers.azure_collector import AzureCollector

            collector = AzureCollector()

            # Fetch real compute metrics
            try:
                idle_vms = collector.get_idle_vms(cpu_threshold=5.0)
                vm_inventory = collector.get_vm_inventory()
                total_vms = len(vm_inventory) if vm_inventory else 0
                idle_count = len(idle_vms) if idle_vms else 0

                if total_vms > 0:
                    rsi = ((total_vms - idle_count) / total_vms) * 100
                else:
                    rsi = 100.0

                compute_metrics = {
                    "rsi": rsi,
                    "total_vms": total_vms,
                    "idle_vms": idle_count,
                    "idle_threshold": 5.0,
                }
            except Exception as e:
                logger.error(f"Failed to fetch compute metrics: {e}")
                print(f"{RED}✗ Error fetching compute metrics: {e}{RESET}")
                return

            # Fetch real storage metrics
            try:
                orphaned_disks = collector.get_orphaned_disks()
                cold_storage = collector.get_cold_storage_candidates()

                disk_count = len(orphaned_disks.get("disks", []))
                # Estimate monthly cost from disk sizes
                monthly_bleed = sum(
                    disk.get("size_gb", 0) * 0.05  # Approx $0.05/GB per month
                    for disk in orphaned_disks.get("disks", [])
                )

                total_cold_gb = sum(c.get("size_gb", 0) for c in cold_storage)

                storage_metrics = {
                    "orphaned_disks": disk_count,
                    "monthly_bleed": monthly_bleed,
                    "cold_storage_gb": total_cold_gb,
                    "cold_storage_count": len(cold_storage),
                }
            except Exception as e:
                logger.error(f"Failed to fetch storage metrics: {e}")
                print(f"{RED}✗ Error fetching storage metrics: {e}{RESET}")
                return

            # Fetch real network metrics
            try:
                orphaned_network = collector.get_orphaned_network_resources()
                orphaned_ips = len(orphaned_network.get("ips", []))
                orphaned_lbs = len(orphaned_network.get("lbs", []))

                network_metrics = {
                    "orphaned_ips": orphaned_ips,
                    "orphaned_lbs": orphaned_lbs,
                    "total_orphaned": orphaned_ips + orphaned_lbs,
                }
            except Exception as e:
                logger.error(f"Failed to fetch network metrics: {e}")
                print(f"{RED}✗ Error fetching network metrics: {e}{RESET}")
                return

        except ImportError as e:
            logger.error(f"Azure collector not available: {e}")
            print(f"{RED}✗ Error: Azure SDK not installed. Run: pip install azure-identity azure-mgmt-compute azure-mgmt-network azure-mgmt-storage azure-mgmt-monitor azure-mgmt-costmanagement{RESET}")
            return
        except Exception as e:
            logger.error(f"Failed to initialize Azure collector: {e}")
            print(f"{RED}✗ Error initializing Azure collector: {e}{RESET}")
            return
    else:
        print(f"{RED}✗ Error: Cloud provider '{cloud_provider}' not yet implemented.{RESET}")
        return

    # Display metrics (only real data)
    _display_compute_metrics(compute_metrics, real_data=True)
    _display_storage_metrics(storage_metrics, real_data=True)
    _display_network_metrics(network_metrics, real_data=True)

    print(f"\n{BOLD}{CYAN}===================================================={RESET}\n")
    print(f"{GREEN}✓ Data Source: Live {cloud_provider.upper()} Cloud Provider API{RESET}\n")


def _display_compute_metrics(metrics: dict, use_real_data: bool):
    """Display compute efficiency metrics."""
    print(f"{BOLD}[COMPUTE EFFICIENCY MATRICES]{RESET}")

    rsi = metrics.get("rsi", 100.0)
    idle_vms = metrics.get("idle_vms", 0)
    total_vms = metrics.get("total_vms", 0)

    if rsi < 50:
        status = f"{RED}{rsi:.1f}% (Critical Over-Provisioning){RESET}"
    elif rsi < 75:
        status = f"{YELLOW}{rsi:.1f}% (Moderate Over-Provisioning){RESET}"
    else:
        status = f"{GREEN}{rsi:.1f}% (Healthy){RESET}"

    print(f"  {BOLD}Compute Right-Sizing Index (RSI):{RESET} {status}")
    print(
        f"    {YELLOW}Description:{RESET} Measures the variance between provisioned instance capacity and actual workloads."
    )

    if idle_vms > 0:
        print(
            f"    {GREEN}Action:{RESET} {idle_vms} of {total_vms} instances are operating below a 5% baseline footprint. Prime candidates for downsizing."
        )
    else:
        print(
            f"    {GREEN}Action:{RESET} All {total_vms} instances are within healthy utilization ranges."
        )
    print("  --------------------------------------------------------------------------------")


def _display_storage_metrics(metrics: dict, use_real_data: bool):
    """Display storage and lifecycle metrics."""
    print(f"{BOLD}[STORAGE & LIFECYCLE OVERHEAD]{RESET}")

    orphaned_disks = metrics.get("orphaned_disks", 0)
    monthly_bleed = metrics.get("monthly_bleed", 0.0)
    cold_storage_gb = metrics.get("cold_storage_gb", 0)

    if orphaned_disks > 0:
        print(
            f"  {BOLD}Orphaned Volume Drain:{RESET} {YELLOW}{orphaned_disks} Detached Disks Detected (${monthly_bleed:.2f}/mo bleed){RESET}"
        )
    else:
        print(f"  {BOLD}Orphaned Volume Drain:{RESET} {GREEN}No Detached Disks Detected{RESET}")

    print(
        f"    {YELLOW}Description:{RESET} Identifies unattached blocks and redundant snapshots no longer tied to active nodes."
    )

    if orphaned_disks > 0:
        print(
            f"    {GREEN}Action:{RESET} Run `cloud-reaper reap --orphaned-disks` to safely deallocate these dead assets."
        )
    else:
        print(f"    {GREEN}Action:{RESET} No action required - storage is properly optimized.")
    print("  --------------------------------------------------------------------------------")

    if cold_storage_gb > 0:
        print(
            f"  {BOLD}Cold Storage Transition Runway:{RESET} {GREEN}{cold_storage_gb:.0f} GB Ready for Migration{RESET}"
        )
    else:
        print(
            f"  {BOLD}Cold Storage Transition Runway:{RESET} {YELLOW}No Cold Storage Candidates Detected{RESET}"
        )

    print(
        f"    {YELLOW}Description:{RESET} Scans object storage frequencies for data pools un-accessed for over 30 days."
    )

    if cold_storage_gb > 0:
        print(
            f"    {GREEN}Action:{RESET} Shifting these blocks from Hot to Archive tiers will lower storage costs by 65%."
        )
    else:
        print(f"    {GREEN}Action:{RESET} Current storage tiering is optimized.")
    print("  --------------------------------------------------------------------------------")


def _display_network_metrics(metrics: dict, use_real_data: bool):
    """Display network and transit metrics."""
    print(f"{BOLD}[NETWORK & TRANSIT ARBITRAGE]{RESET}")

    orphaned_ips = metrics.get("orphaned_ips", 0)
    orphaned_lbs = metrics.get("orphaned_lbs", 0)
    total_orphaned = metrics.get("total_orphaned", 0)

    if total_orphaned > 0:
        print(
            f"  {BOLD}Orphaned Network Resources:{RESET} {YELLOW}{orphaned_ips} Public IPs + {orphaned_lbs} Load Balancers Detected{RESET}"
        )
        print(
            f"    {YELLOW}Description:{RESET} Identifies unattached network resources that incur costs without providing value."
        )
        print(
            f"    {GREEN}Action:{RESET} Review and remove orphaned network resources to reduce monthly costs."
        )
    else:
        print(f"  {BOLD}Orphaned Network Resources:{RESET} {GREEN}None Detected{RESET}")
        print(
            f"    {YELLOW}Description:{RESET} No unattached network resources found in current inventory."
        )
        print(f"    {GREEN}Action:{RESET} Network resources are properly utilized.")


if __name__ == "__main__":
    display_finops_performance_metrics()
