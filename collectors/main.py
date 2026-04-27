import os
from dotenv import load_dotenv
from collectors.aws_collector import AWSCollector
from collectors.azure_collector import AzureCollector
from engine.calculator import CostCalculator

# Load environment variables
load_dotenv()

def run_reaper():
    print("="*40)
    print("        CLOUD REAPER v1.0        ")
    print("="*40)

    # Initialize Engine
    calc = CostCalculator()
    
    # --- AZURE SCAN ---
    print("\n[+] Initializing Azure Scan...")
    az = AzureCollector()
    az_vms = az.get_vm_inventory()
    az_orphans = az.get_orphaned_disks()
    
    az_monthly = 0
    for vm in az_vms:
        cost = calc.calculate_monthly_cost('azure', 'vm', vm['size'])
        az_monthly += cost
    
    for disk in az_orphans:
        # Simplified mapping for demonstration
        cost = calc.calculate_monthly_cost('azure', 'disk', 'premium_ssd_p6_64gb')
        az_monthly += cost
        print(f"  [!] Orphaned Disk Found: {disk['name']} -> Potential Saving: ${cost:.2f}/mo")

    # --- AWS SCAN ---
    print("\n[+] Initializing AWS Scan...")
    aws = AWSCollector()
    aws_instances = aws.get_ec2_inventory()
    aws_orphans = aws.get_orphaned_volumes()
    
    aws_monthly = 0
    for ins in aws_instances:
        cost = calc.calculate_monthly_cost('aws', 'ec2', ins['type'])
        aws_monthly += cost

    for vol in aws_orphans:
        cost = calc.calculate_monthly_cost('aws', 'ebs', 'gp3_per_gb_month', vol['size'])
        aws_monthly += cost
        print(f"  [!] Orphaned Volume Found: {vol['id']} -> Potential Saving: ${cost:.2f}/mo")

    # --- FINAL REPORT ---
    print("\n" + "="*40)
    print(f"TOTAL PROJECTED MONTHLY BURN: ${az_monthly + aws_monthly:.2f}")
    print(f"  - Azure: ${az_monthly:.2f}")
    print(f"  - AWS:   ${aws_monthly:.2f}")
    print("="*40)

if __name__ == "__main__":
    run_reaper()