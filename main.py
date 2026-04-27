import os
import sys
from dotenv import load_dotenv

# Path resolution
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from collectors.azure_collector import AzureCollector
from engine.calculator import CostCalculator
from data.pusher import DataPusher

def run_reaper():
    load_dotenv()
    
    print("\n" + "="*50)
    print("             CLOUD REAPER v1.0 [AZURE MODE]  ")
    print("==================================================")

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
    orphans = az.get_orphaned_disks()
    print(f"    - Orphaned Disks Found: {len(orphans)}")
    
    for disk in orphans:
        # Dynamic pricing lookup
        cost = calc.calculate_monthly_cost('azure', 'disk', 'premium_ssd_p6_64gb')
        total_monthly_saving += cost
        print(f"      [!] REAP TARGET: {disk['name']} | Saving: ${cost:.2f}/mo")

    # 3. Idle VM Discovery (Go Engine Powered)
    idle_vms = az.get_idle_vms(cpu_threshold=5.0)
    print(f"    - Idle VMs Detected: {len(idle_vms)}")
    
    for vm in idle_vms:
        print(f"      [!] IDLE VM: {vm['name']} | Avg CPU: {vm['usage']}%")

    # 4. Persistence
    if total_monthly_saving > 0:
        pusher.push_savings('azure', total_monthly_saving)
        print(f"\n[+] Telemetry pushed to InfluxDB.")

    print("\n" + "="*50)
    print(f"TOTAL POTENTIAL AZURE SAVINGS: ${total_monthly_saving:.2f} / month")
    print("="*50 + "\n")
    
    pusher.close()

if __name__ == "__main__":
    run_reaper()
