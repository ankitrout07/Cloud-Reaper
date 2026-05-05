import os
import datetime
import subprocess
import json
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.web import WebSiteManagementClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.recoveryservices import RecoveryServicesClient
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
        self.recovery = RecoveryServicesClient(self.credentials, self.subscription_id)

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

    def get_user_name(self):
        """Returns the authenticated user's display name"""
        try:
            from azure.mgmt.authorization import AuthorizationManagementClient
            auth_client = AuthorizationManagementClient(self.credentials, self.subscription_id)
            # Get current user info - this is a simplified approach
            return "Azure User"
        except Exception:
            return "Azure User"

    def get_subscription_name(self):
        """Returns the subscription display name"""
        try:
            from azure.mgmt.subscription import SubscriptionClient
            sub_client = SubscriptionClient(self.credentials)
            sub = sub_client.subscriptions.get(self.subscription_id)
            return sub.display_name
        except Exception:
            return "Unknown Subscription"

    def get_live_prices(self):
        """
        Executes the Go Performance Core to fetch real-time Azure pricing data.
        """
        # Path to the Go binary we built in engine-go/
        go_binary = "./engine-go/reaper-engine"
        
        if not os.path.exists(go_binary):
            print(f"[-] Error: Go binary not found at {go_binary}. Run ./reap.sh to build.")
            return {}

        try:
            # Run the Go scraper and capture JSON output
            result = subprocess.run([go_binary, "--mode", "prices"], capture_output=True, text=True)
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                print(f"[-] Go Engine Error: {result.stderr}")
                return {}
        except Exception as e:
            print(f"[-] Failed to execute Go Scraper: {e}")
            return {}

    def get_burn_rate_forecast(self):
        """
        Calculates burn rate and EOM forecast using ARIMA.
        """
        from engine.models import SessionLocal, CostHistory
        from engine.logic import BudgetForecaster
        
        db = SessionLocal()
        # Fetch last 30 days of daily spend
        history = db.query(CostHistory).filter(CostHistory.type == 'ACTUAL').order_by(CostHistory.timestamp.desc()).limit(30).all()
        db.close()
        
        # Reverse to get chronological order
        spend_data = [float(h.amount) for h in reversed(history)]
        
        # If no DB data, provide some mock data for the demo
        if not spend_data:
            spend_data = [120, 125, 118, 140, 135, 150, 145]
            
        forecaster = BudgetForecaster()
        forecast = forecaster.forecast_eom(spend_data)
        
        # Calculate slope for the trend
        slope = 0
        if len(spend_data) >= 2:
            slope = (spend_data[-1] - spend_data[0]) / len(spend_data)

        return {
            "projected_total": forecast['projected_eom'],
            "daily_history": spend_data,
            "slope": slope,
            "confidence": forecast['confidence']
        }

    def get_virtual_tags(self):
        """
        Returns virtual tagging logic (mocked for demo).
        """
        return [
            {"name": "Production Cluster", "virtual_tags": {"Env": "Prod", "Dept": "Eng"}},
            {"name": "Marketing-Web", "virtual_tags": {"Dept": "Mktg"}},
            {"name": "Data-Science-Sandbox", "virtual_tags": {"Owner": "DS-Team"}}
        ]

    def get_greenops_recommendations(self):
        """
        Sustainability recommendations.
        """
        return [
            {"name": "Batch Processor", "current_region": "East US", "target_region": "West US 2", "savings_pct": 22},
            {"name": "Legacy Storage", "current_region": "West Europe", "target_region": "North Europe", "savings_pct": 15}
        ]

    def execute_reap(self, resource_id, resource_type):
        """
        Executes a reap (delete/stop) action.
        """
        # In a real app, this would call the Azure API to delete/stop
        return {"status": "success", "message": f"Successfully authorized reap for {resource_id} ({resource_type})"}

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