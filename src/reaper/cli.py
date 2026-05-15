import os

from dotenv import load_dotenv

from reaper.collectors.azure_collector import AzureCollector
from reaper.engine.calculator import CostCalculator
from reaper.engine.logic import ZombieScorer
from reaper.services.pusher import DataPusher

# Constants
MIN_SUB_ID_LEN = 5
FALLBACK_PREMIUM_DISK_COST = 5.89
FALLBACK_STANDARD_DISK_COST = 1.54
ZOMBIE_CPU_THRESHOLD = 5.0


def print_banner(error_id=None):
    """Prints the application banner."""
    print("\n" + "=" * 50)
    print("             CLOUD REAPER v1.0 [AZURE MODE]  ")
    print("==================================================")
    if error_id:
        print("\n[!] CONFIGURATION ERROR: Azure Subscription ID is invalid.")
        print(f"    Current ID: {error_id}")
        print("\n    Please update your .env file with a real Subscription ID.")
        print("    Or launch the Dashboard to use the Onboarding Wizard:")
        print("    python3 -m reaper.web.app")
        print("\n" + "=" * 50 + "\n")


def run_reaper():
    """Main execution loop for the Reaper CLI."""
    load_dotenv(override=True)

    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    if not sub_id or "your_" in sub_id or len(sub_id) < MIN_SUB_ID_LEN:
        print_banner(error_id=sub_id)
        return

    print_banner()

    calc = CostCalculator()
    pusher = DataPusher()
    total_monthly_saving = 0.0

    print("\n[+] AZURE: Initializing Resource Inventory...")
    az = AzureCollector()

    # Load live prices from Go engine into calculator
    print("    - Fetching Live Prices (Go Scraper)...")
    live_prices = az.get_live_prices()
    calc.load_prices(live_prices)
    print(f"    - Loaded {len(live_prices)} live price items.")

    # 1. Compute Inventory
    vms = az.get_vm_inventory()
    print(f"    - Active VMs Found: {len(vms)}")

    # 2. Storage Inventory (Reap Targets)
    disks = az.get_orphaned_disks()
    print(f"    - Orphaned Disks Found: {len(disks)}")

    for disk in disks:
        # Dynamic pricing lookup - Normalize SKU for lookup
        sku_lookup = disk["tier"].lower().replace(" ", "_")
        cost = calc.calculate_monthly_cost("azure", "disk", sku_lookup)

        if cost == 0:
            # Fallback for common tiers
            cost = (
                FALLBACK_PREMIUM_DISK_COST
                if "premium" in sku_lookup
                else FALLBACK_STANDARD_DISK_COST
            )

        total_monthly_saving += cost
        print(f"      [!] REAP TARGET: {disk['name']} | Saving: ${cost:.2f}/mo")

    # 3. Idle VM Discovery (Go Engine Powered)
    idle_vms = az.get_idle_vms(cpu_threshold=ZOMBIE_CPU_THRESHOLD)
    print(f"    - Idle VMs Detected: {len(idle_vms)}")

    for vm in idle_vms:
        print(f"      [!] IDLE VM: {vm['name']} | Avg CPU: {vm['average_cpu']}%")

    # 4. Zombie Reaper (Heuristic Scoring)
    print("\n[+] ZOMBIE: Executing Heuristic Analysis...")
    scorer = ZombieScorer()

    # Check VMs for Zombie behavior
    for vm_name in [v["name"] for v in vms]:
        vm_data = {
            "name": vm_name,
            "type": "VirtualMachine",
            "is_unattached": False,
            "iops_history": [],  # Real metrics would be fetched here or in Scorer
        }
        res = scorer.score_resource(vm_data)
        if res["is_zombie"]:
            print(f"      [🚨] ZOMBIE DETECTED: {vm_name} (Score: {res['score']})")

    # Check Disks
    for disk in disks.get("disks", []):
        disk_data = {
            "name": disk["name"],
            "type": "Disk",
            "is_unattached": True,
            "iops_history": [],
        }
        res = scorer.score_resource(disk_data)
        if res["is_zombie"]:
            print(f"      [🚨] ZOMBIE DETECTED: {disk['name']} (Score: {res['score']})")

    # 5. Persistence
    if total_monthly_saving > 0:
        pusher.push_savings("azure", total_monthly_saving)
        print("\n[+] Telemetry pushed to InfluxDB.")

    print("\n" + "=" * 50)
    print(f"TOTAL POTENTIAL AZURE SAVINGS: ${total_monthly_saving:.2f} / month")
    print("=" * 50 + "\n")

    pusher.close()


if __name__ == "__main__":
    run_reaper()
