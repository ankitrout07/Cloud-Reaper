import os
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from dotenv import load_dotenv

load_dotenv()

class AzureCollector:
    def __init__(self):
        self.subscription_id = os.getenv('AZURE_SUBSCRIPTION_ID')
        self.credentials = DefaultAzureCredential()
        # Only initialize client if subscription_id exists to avoid immediate crash
        if self.subscription_id:
            self.compute_client = ComputeManagementClient(self.credentials, self.subscription_id)
        else:
            self.compute_client = None

    def get_vm_inventory(self):
        if not self.compute_client: return []
        try:
            vms = self.compute_client.virtual_machines.list_all()
            return [{'name': vm.name, 'size': vm.hardware_profile.vm_size} for vm in vms]
        except Exception:
            return []

    def get_orphaned_disks(self):
        if not self.compute_client: return []
        try:
            disks = self.compute_client.disks.list()
            return [{'name': d.name, 'size_gb': d.disk_size_gb} for d in disks if d.managed_by is None]
        except Exception:
            return []
