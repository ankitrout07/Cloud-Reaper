import os
import sys
from dotenv import load_dotenv

# Ensure local modules can be found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from collectors.aws_collector import AWSCollector
from collectors.azure_collector import AzureCollector
from engine.calculator import CostCalculator

def run_reaper():
    load_dotenv()
    
    print("\n" + "="*50)
    print("             CLOUD REAPER v1.0              ")
    print("      FinOps & Cost Optimization Engine     ")
    print("="*50)

    calc = CostCalculator()
    total_monthly_saving = 0.0

    # --- AZURE PILLAR ---
    print("\n[+] AZURE: Initializing Resource Inventory...")
    try:
        az = AzureCollector()
        vms = az.get_vm_inventory()
        orphans = az.get_orphaned_disks()
        
        print(f"    - Active VMs: {len(vms)}")
        print(f"    - Orphaned Disks: {len(orphans)}")
        
        for disk in orphans:
            # Pricing based on our engine/price_book.yaml mapping
            cost = calc.calculate_monthly_cost('azure', 'disk', 'premium_ssd_p6_64gb')
            total_monthly_saving += cost
            print(f"      [!] REAP TARGET: {disk['name']} ({disk['size_gb']}GB) | Saving: ${cost:.2f}/mo")
    except Exception as e:
        print(f"    [!] Azure Scan Error: {e}")

    # --- AWS PILLAR ---
    print("\n[+] AWS: Initializing Resource Inventory...")
    try:
        aws = AWSCollector()
        instances = aws.get_ec2_inventory()
        vol_orphans = aws.get_orphaned_volumes()
        
        print(f"    - Active Instances: {len(instances)}")
        print(f"    - Orphaned Volumes: {len(vol_orphans)}")
        
        for vol in vol_orphans:
            cost = calc.calculate_monthly_cost('aws', 'ebs', 'gp3_per_gb_month', vol['size'])
            total_monthly_saving += cost
            print(f"      [!] REAP TARGET: {vol['id']} ({vol['size']}GB) | Saving: ${cost:.2f}/mo")
    except Exception as e:
        print(f"    [!] AWS Scan Error: {e}")

    # --- SUMMARY ---
    print("\n" + "="*50)
    print(f"TOTAL POTENTIAL REAPING SAVINGS: ${total_monthly_saving:.2f} / month")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_reaper()
