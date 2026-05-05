import os

from reaper.collectors.azure_collector import AzureCollector

def run_test():
    # Force set the subscription ID for this test
    os.environ["AZURE_SUBSCRIPTION_ID"] = "7ef42162-83d2-4247-8010-38bf34dd1453"

    az = AzureCollector()
    print(f"Scanning subscription: {az.subscription_id}")

    vms = az.get_vm_inventory()
    print(f"Found {len(vms)} VMs: {[v['name'] for v in vms]}")

    orphans = az.get_orphaned_disks()
    print(f"Found {len(orphans)} Orphaned Disks: {[d['name'] for d in orphans]}")

    idle = az.get_idle_vms()
    print(f"Found {len(idle)} Idle VMs: {[v['name'] for v in idle]}")


if __name__ == "__main__":
    run_test()
