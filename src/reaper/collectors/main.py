import sys
from pathlib import Path

from dotenv import load_dotenv

# Set PYTHONPATH to include src directory if running as a script
# But in a professional structure, we should run with `python -m reaper.collectors.main`
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

try:
    from reaper.collectors.aws_collector import AWSCollector
    from reaper.collectors.azure_collector import AzureCollector
    from reaper.engine.calculator import CostCalculator

    print(">>> CORE: Modules imported successfully")
except Exception as e:
    print(f">>> ERROR: Import failed: {e}")
    sys.exit(1)

load_dotenv()


def run_reaper():
    print("\n" + "=" * 40)
    print("        CLOUD REAPER v1.0        ")
    print("=" * 40)

    CostCalculator()

    # --- AZURE SCAN ---
    print("\n[+] Initializing Azure Scan...")
    try:
        az = AzureCollector()
        vms = az.get_vm_inventory()
        print(f"    Found {len(vms)} VMs")
    except Exception as e:
        print(f"    [!] Azure Scan Failed: {e}")

    # --- AWS SCAN ---
    print("\n[+] Initializing AWS Scan...")
    try:
        aws = AWSCollector()
        instances = aws.get_ec2_inventory()
        print(f"    Found {len(instances)} EC2 Instances")
    except Exception as e:
        print(f"    [!] AWS Scan Failed: {e}")

    print("\n" + "=" * 40)
    print("SCAN COMPLETE")
    print("=" * 40)


if __name__ == "__main__":
    print(">>> CORE: Entering __main__ block")
    run_reaper()
