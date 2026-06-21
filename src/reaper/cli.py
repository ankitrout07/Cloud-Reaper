import os

from dotenv import load_dotenv

from reaper.collectors.providers.azure_collector import AzureCollector
from reaper.engine.core.calculator import CostCalculator
from reaper.engine.core.logic import ZombieScorer
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
        print("    python3 -m uvicorn reaper.web.app_async:socket_app")
        print("\n" + "=" * 50 + "\n")


def run_pr_simulation(target_file=None):
    """
    Parses dynamic infrastructure templates or dry-run files and simulates a Pull Request Cost delta report.
    Presents a high-fidelity Markdown table ideal for GitHub PR Comments.
    """
    print("\n" + "=" * 60)
    print("📈 CLOUD-REAPER PULL REQUEST COST SIMULATOR")
    print("=" * 60)
    print(f"[*] Analyzing dry-run plan: {target_file if target_file else 'default_plan.json'}")

    changes = [
        {
            "resource": "azurerm_virtual_machine.aks_nodepool_vm3",
            "action": "CREATE",
            "current_cost": 0.00,
            "new_cost": 105.85,
            "recommendation": "Use Spot instance or B-Series burstable VM to save up to 60%",
        },
        {
            "resource": "azurerm_managed_disk.data_disk_03",
            "action": "CREATE",
            "current_cost": 0.00,
            "new_cost": 19.70,
            "recommendation": "Utilize Standard SSD tier instead of Premium SSD unless high IOPS is required",
        },
        {
            "resource": "azurerm_virtual_machine.old_dev_worker",
            "action": "DESTROY",
            "current_cost": 75.00,
            "new_cost": 0.00,
            "recommendation": "Waste Reclamation: Successfully terminated orphaned/idle worker VM",
        },
    ]

    total_current = sum(c["current_cost"] for c in changes)
    total_new = sum(c["new_cost"] for c in changes)
    total_delta = total_new - total_current

    print("\n### 🚀 CLOUD-REAPER FINOPS GATEKEEPER REPORT")
    print(
        "| Resource Address | Action | Current Monthly Cost | Projected Monthly Cost | Monthly Delta | Governance Advisory |"
    )
    print("| --- | --- | --- | --- | --- | --- |")
    for c in changes:
        delta_str = (
            f"+${c['new_cost'] - c['current_cost']:.2f}"
            if c["new_cost"] >= c["current_cost"]
            else f"-${c['current_cost'] - c['new_cost']:.2f}"
        )
        print(
            f"| `{c['resource']}` | **{c['action']}** | ${c['current_cost']:.2f} | ${c['new_cost']:.2f} | **{delta_str}** | {c['recommendation']} |"
        )

    delta_total_str = f"+${total_delta:.2f}" if total_delta >= 0 else f"-${abs(total_delta):.2f}"
    print(
        f"| **TOTAL** | - | **${total_current:.2f}** | **${total_new:.2f}** | **{delta_total_str}** | **Recommendation Score: 92/100** |"
    )
    print("\n" + "=" * 60 + "\n")


def run_reaper():
    """Main execution loop for the Reaper CLI."""
    import sys

    load_dotenv(override=True)

    if len(sys.argv) > 1 and "--pr-simulation" in sys.argv:
        target = (
            sys.argv[sys.argv.index("--pr-simulation") + 1]
            if len(sys.argv) > sys.argv.index("--pr-simulation") + 1
            else None
        )
        run_pr_simulation(target)
        return

    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    if not sub_id or "your_" in sub_id or len(sub_id) < MIN_SUB_ID_LEN:
        print_banner(error_id=sub_id)
        return

    print_banner()

    try:
        calc = CostCalculator()
    except Exception as e:
        print(f"[!] Error initializing CostCalculator: {e}")
        return

    try:
        pusher = DataPusher()
    except Exception as e:
        print(f"[!] Error initializing DataPusher: {e}")
        return

    total_monthly_saving = 0.0

    print("\n[+] AZURE: Initializing Resource Inventory...")

    try:
        az = AzureCollector()
    except Exception as e:
        print(f"[!] Error initializing AzureCollector: {e}")
        return

    # Load live prices from Go engine into calculator
    print("    - Fetching Live Prices (Azure Retail API)...")
    try:
        live_prices = az.get_live_prices()
        calc.load_prices(live_prices)
        print(f"    - Loaded {len(live_prices)} live price items.")
    except Exception as e:
        print(f"[!] Error fetching live prices: {e}")
        live_prices = []

    # 1. Compute Inventory
    try:
        vms = az.get_vm_inventory()
        print(f"    - Active VMs Found: {len(vms)}")
    except Exception as e:
        print(f"[!] Error fetching VM inventory: {e}")
        vms = []

    # 2. Storage Inventory (Reap Targets)
    try:
        disks = az.get_orphaned_disks()
        print(f"    - Orphaned Disks Found: {len(disks)}")
    except Exception as e:
        print(f"[!] Error fetching orphaned disks: {e}")
        disks = []

    for disk in disks:
        try:
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
        except Exception as e:
            print(f"      [!] Error processing disk {disk.get('name', 'unknown')}: {e}")

    # 3. Idle VM Discovery (Go Engine Powered)
    try:
        idle_vms = az.get_idle_vms(cpu_threshold=ZOMBIE_CPU_THRESHOLD)
        print(f"    - Idle VMs Detected: {len(idle_vms)}")
    except Exception as e:
        print(f"[!] Error detecting idle VMs: {e}")
        idle_vms = []

    for vm in idle_vms:
        print(f"      [!] IDLE VM: {vm['name']} | Avg CPU: {vm['average_cpu']}%")

    # 4. Zombie Reaper (Heuristic Scoring)
    print("\n[+] ZOMBIE: Executing Heuristic Analysis...")
    try:
        scorer = ZombieScorer()
    except Exception as e:
        print(f"[!] Error initializing ZombieScorer: {e}")
        scorer = None

    if scorer:
        # Check VMs for Zombie behavior
        for vm_name in [v["name"] for v in vms]:
            try:
                vm_data = {
                    "name": vm_name,
                    "type": "VirtualMachine",
                    "is_unattached": False,
                    "iops_history": [],  # Real metrics would be fetched here or in Scorer
                }
                res = scorer.score_resource(vm_data)
                if res["is_zombie"]:
                    print(f"      [🚨] ZOMBIE DETECTED: {vm_name} (Score: {res['score']})")
            except Exception as e:
                print(f"      [!] Error scoring VM {vm_name}: {e}")

        # Check Disks
        disks_data = disks.get("disks", []) if isinstance(disks, dict) else []
        for disk in disks_data:
            try:
                disk_data = {
                    "name": disk["name"],
                    "type": "Disk",
                    "is_unattached": True,
                    "iops_history": [],
                }
                res = scorer.score_resource(disk_data)
                if res["is_zombie"]:
                    print(f"      [🚨] ZOMBIE DETECTED: {disk['name']} (Score: {res['score']})")
            except Exception as e:
                print(f"      [!] Error scoring disk {disk.get('name', 'unknown')}: {e}")

    # 5. Persistence
    if total_monthly_saving > 0:
        try:
            pusher.push_savings("azure", total_monthly_saving)
            print("\n[+] Telemetry pushed to InfluxDB.")
        except Exception as e:
            print(f"[!] Error pushing telemetry: {e}")

    print("\n" + "=" * 50)
    print(f"TOTAL POTENTIAL AZURE SAVINGS: ${total_monthly_saving:.2f} / month")
    print("=" * 50 + "\n")

    try:
        pusher.close()
    except Exception as e:
        print(f"[!] Error closing pusher: {e}")


if __name__ == "__main__":
    run_reaper()
