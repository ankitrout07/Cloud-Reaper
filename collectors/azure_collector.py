import os
import datetime
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.web import WebSiteManagementClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.recoveryservices import RecoveryServicesManagementClient
from dotenv import load_dotenv

load_dotenv()

class AzureCollector:
    def __init__(self):
        self.subscription_id = os.getenv('AZURE_SUBSCRIPTION_ID')
        self.credentials = DefaultAzureCredential()
        self.compute = ComputeManagementClient(self.credentials, self.subscription_id)
        self.network = NetworkManagementClient(self.credentials, self.subscription_id)
        self.monitor = MonitorManagementClient(self.credentials, self.subscription_id)
        self.web = WebSiteManagementClient(self.credentials, self.subscription_id)
        self.sql = SqlManagementClient(self.credentials, self.subscription_id)
        self.recovery = RecoveryServicesManagementClient(self.credentials, self.subscription_id)

    def get_vm_inventory(self):
        """Fetches all VMs and their sizes."""
        vms = self.compute.virtual_machines.list_all()
        inventory = []
        for vm in vms:
            inventory.append({
                'name': vm.name,
                'size': vm.hardware_profile.vm_size,
                'location': vm.location,
                'status': 'Managed'
            })
        return inventory

    def get_idle_vms(self, cpu_threshold=5.0):
        """Finds VMs with avg CPU utilization below threshold over last 7 days."""
        vms = self.compute.virtual_machines.list_all()
        idle_vms = []

        end_time = datetime.datetime.utcnow()
        start_time = end_time - datetime.timedelta(days=7)

        for vm in vms:
            resource_group = vm.id.split('/')[4]
            resource_id = f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm.name}"

            metrics = self.monitor.metrics.list(
                resource_id,
                timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                interval='PT12H',
                metricnames='Percentage CPU',
                aggregation='Average'
            )

            for item in metrics.value:
                for timeseries in item.timeseries:
                    data_points = [point.average for point in timeseries.data if point.average is not None]
                    if not data_points:
                        continue
                    avg_usage = sum(data_points) / len(data_points)
                    if avg_usage < cpu_threshold:
                        idle_vms.append({
                            'name': vm.name,
                            'resource_group': resource_group,
                            'average_cpu': round(avg_usage, 2)
                        })
                        break
        return idle_vms

    def get_orphaned_network_resources(self):
        """Monitors Public IPs and Load Balancers with zero associations."""
        ips = self.network.public_ip_addresses.list_all()
        lbs = self.network.load_balancers.list_all()

        waste = {
            'ips': [ip.name for ip in ips if ip.ip_configuration is None],
            'lbs': [lb.name for lb in lbs if not lb.backend_address_pools or all(len(pool.backend_ip_configurations or []) == 0 for pool in lb.backend_address_pools)]
        }
        return waste

    def get_orphaned_disks(self):
        """Identifies disks that are NOT attached to any VM."""
        disks = self.compute.disks.list()
        orphans = []
        for disk in disks:
            if disk.managed_by is None:
                orphans.append({
                    'name': disk.name,
                    'size_gb': disk.disk_size_gb,
                    'tier': disk.sku.name
                })
        return orphans

    def get_unassociated_ips(self):
        """Finds Public IPs not attached to any NIC/Resource"""
        ips = self.network.public_ip_addresses.list_all()
        unassociated = []
        for ip in ips:
            if ip.ip_configuration is None:
                unassociated.append({
                    'name': ip.name,
                    'location': ip.location,
                    'sku': ip.sku.name if ip.sku else 'Basic'
                })
        return unassociated

    def get_idle_load_balancers(self):
        """Finds LBs with no backend pool members"""
        lbs = self.network.load_balancers.list_all()
        idle_lbs = []
        for lb in lbs:
            if not lb.backend_address_pools or all(len(pool.backend_ip_configurations or []) == 0 for pool in lb.backend_address_pools):
                idle_lbs.append({
                    'name': lb.name,
                    'location': lb.location,
                    'sku': lb.sku.name if lb.sku else 'Basic'
                })
        return idle_lbs

    def get_snapshots(self):
        """Finds snapshots that might be orphaned"""
        snapshots = self.compute.snapshots.list()
        return [{'name': s.name, 'size_gb': s.disk_size_gb, 'location': s.location} for s in snapshots]

    def get_idle_app_gateways(self):
        """Finds App Gateways with no backend pools or idle"""
        gateways = self.network.application_gateways.list_all()
        idle_gateways = []
        for gw in gateways:
            if not gw.backend_address_pools or all(len(pool.backend_addresses or []) == 0 for pool in gw.backend_address_pools):
                idle_gateways.append({
                    'name': gw.name,
                    'location': gw.location,
                    'sku': f"{gw.sku.name}_{gw.sku.tier}"
                })
        return idle_gateways

    def get_recovery_vaults(self):
        """Finds Recovery Service Vaults"""
        vaults = self.recovery.vaults.list_by_subscription_id(self.subscription_id)
        return [{'name': v.name, 'location': v.location, 'sku': v.sku.name} for v in vaults]

    def get_empty_app_service_plans(self):
        """Finds App Service Plans with 0 apps assigned"""
        plans = self.web.app_service_plans.list()
        empty_plans = []
        for plan in plans:
            if getattr(plan, 'number_of_sites', 0) == 0:
                empty_plans.append({
                    'name': plan.name,
                    'location': plan.location,
                    'sku': plan.sku.name,
                    'tier': plan.sku.tier
                })
        return empty_plans

    def get_sql_databases(self):
        """Finds SQL Databases - TODO: Add idle check with metrics"""
        servers = self.sql.servers.list()
        databases = []
        for server in servers:
            dbs = self.sql.databases.list_by_server(server.resource_group_name, server.name)
            for db in dbs:
                if db.name != 'master':
                    databases.append({
                        'name': db.name,
                        'server': server.name,
                        'location': db.location,
                        'sku': db.sku.name if db.sku else 'Unknown'
                    })
        return databases

if __name__ == "__main__":
    collector = AzureCollector()
    print("--- Scanning Azure VMs ---")
    for vm in collector.get_vm_inventory():
        print(f"Found VM: {vm['name']} [{vm['size']}]")

    print("\n--- Hunting Idle VMs ---")
    idle_vms = collector.get_idle_vms()
    if not idle_vms:
        print("No idle VMs found.")
    for vm in idle_vms:
        print(f"[!] IDLE VM: {vm['name']} in RG {vm['resource_group']} - CPU avg {vm['average_cpu']}%")

    print("\n--- Hunting Orphaned Network Resources ---")
    orphaned_network = collector.get_orphaned_network_resources()
    if not orphaned_network['ips'] and not orphaned_network['lbs']:
        print("No unassociated network waste found.")
    for ip in orphaned_network['ips']:
        print(f"[!] REAPER TARGET: Unassociated IP {ip}")
    for lb in orphaned_network['lbs']:
        print(f"[!] REAPER TARGET: Idle LB {lb}")

    print("\n--- Hunting Orphaned Disks ---")
    orphans = collector.get_orphaned_disks()
    if not orphans:
        print("No orphaned disks found. Infrastructure is clean.")
    for disk in orphans:
        print(f"[!] REAPER TARGET: {disk['name']} ({disk['size_gb']}GB) - Tier: {disk['tier']}")

    print("\n--- Hunting Unassociated Public IPs ---")
    unassociated_ips = collector.get_unassociated_ips()
    if not unassociated_ips:
        print("No unassociated public IPs found.")
    for ip in unassociated_ips:
        print(f"[!] REAPER TARGET: {ip['name']} - Location: {ip['location']}, SKU: {ip['sku']}")

    print("\n--- Hunting Idle Load Balancers ---")
    idle_lbs = collector.get_idle_load_balancers()
    if not idle_lbs:
        print("No idle load balancers found.")
    for lb in idle_lbs:
        print(f"[!] REAPER TARGET: {lb['name']} - Location: {lb['location']}, SKU: {lb['sku']}")

    print("\n--- Hunting Snapshots ---")
    snapshots = collector.get_snapshots()
    if not snapshots:
        print("No snapshots found.")
    for snap in snapshots:
        print(f"Snapshot: {snap['name']} ({snap['size_gb']}GB) - Location: {snap['location']}")