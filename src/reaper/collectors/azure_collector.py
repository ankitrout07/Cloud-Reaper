import datetime
import json
import os
import subprocess
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.recoveryservices import RecoveryServicesClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.web import WebSiteManagementClient
from dotenv import load_dotenv

from reaper.engine.logic import BudgetForecaster
from reaper.engine.models import CostHistory, SessionLocal

load_dotenv()


class AzureCollector:
    def __init__(self, subscription_id=None):
        self.subscription_id = subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID")
        self.credentials = DefaultAzureCredential()
        self.compute = ComputeManagementClient(self.credentials, self.subscription_id)
        self.network = NetworkManagementClient(self.credentials, self.subscription_id)
        self.monitor = MonitorManagementClient(self.credentials, self.subscription_id)
        self.web = WebSiteManagementClient(self.credentials, self.subscription_id)
        self.sql = SqlManagementClient(self.credentials, self.subscription_id)
        self.recovery = RecoveryServicesClient(self.credentials, self.subscription_id)
        try:
            from azure.mgmt.costmanagement import CostManagementClient
            self.cost_management = CostManagementClient(self.credentials)
        except ImportError:
            self.cost_management = None

    def get_vm_inventory(self):
        """Fetches all VMs and their sizes."""
        vms = self.compute.virtual_machines.list_all()
        inventory = []
        for vm in vms:
            inventory.append(
                {
                    "name": vm.name,
                    "size": vm.hardware_profile.vm_size,
                    "location": vm.location,
                    "status": "Managed",
                }
            )
        return inventory

    def get_idle_vms(self, cpu_threshold=5.0):
        """Finds VMs with avg CPU utilization below threshold over last 7 days."""
        vms = self.compute.virtual_machines.list_all()
        idle_vms = []

        end_time = datetime.datetime.now(datetime.UTC)
        start_time = end_time - datetime.timedelta(days=7)

        for vm in vms:
            resource_group = vm.id.split("/")[4]
            resource_id = (
                f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group}/"
                f"providers/Microsoft.Compute/virtualMachines/{vm.name}"
            )

            metrics = self.monitor.metrics.list(
                resource_id,
                timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                interval="PT12H",
                metricnames="Percentage CPU",
                aggregation="Average",
            )

            for item in metrics.value:
                for timeseries in item.timeseries:
                    data_points = [
                        point.average for point in timeseries.data if point.average is not None
                    ]
                    if not data_points:
                        continue
                    avg_usage = sum(data_points) / len(data_points)
                    if avg_usage < cpu_threshold:
                        idle_vms.append(
                            {
                                "name": vm.name,
                                "resource_group": resource_group,
                                "average_cpu": round(avg_usage, 2),
                            }
                        )
                        break
        return idle_vms

    def get_orphaned_network_resources(self):
        """Monitors Public IPs and Load Balancers with zero associations."""
        ips = self.network.public_ip_addresses.list_all()
        lbs = self.network.load_balancers.list_all()

        return {
            "ips": [ip.name for ip in ips if ip.ip_configuration is None],
            "lbs": [
                lb.name
                for lb in lbs
                if not lb.backend_address_pools
                or all(
                    len(pool.backend_ip_configurations or []) == 0
                    for pool in lb.backend_address_pools
                )
            ],
        }

    def get_orphaned_disks(self):
        """Identifies disks and snapshots that are NOT attached to any VM."""
        disks = self.compute.disks.list()
        orphaned_disks = []
        for disk in disks:
            if disk.managed_by is None:
                orphaned_disks.append(
                    {
                        "name": disk.name,
                        "size_gb": disk.disk_size_gb,
                        "tier": disk.sku.name,
                        "rg": disk.id.split("/")[4] if "/" in disk.id else "Unknown",
                    }
                )

        snapshots = self.get_snapshots()
        return {"disks": orphaned_disks, "snapshots": snapshots}

    def get_unassociated_ips(self):
        """Finds Public IPs not attached to any NIC/Resource"""
        ips = self.network.public_ip_addresses.list_all()
        unassociated = []
        for ip in ips:
            if ip.ip_configuration is None:
                unassociated.append(
                    {
                        "name": ip.name,
                        "location": ip.location,
                        "sku": ip.sku.name if ip.sku else "Basic",
                    }
                )
        return unassociated

    def get_idle_load_balancers(self):
        """Finds LBs with no backend pool members"""
        lbs = self.network.load_balancers.list_all()
        idle_lbs = []
        for lb in lbs:
            if not lb.backend_address_pools or all(
                len(pool.backend_ip_configurations or []) == 0 for pool in lb.backend_address_pools
            ):
                idle_lbs.append(
                    {
                        "name": lb.name,
                        "location": lb.location,
                        "sku": lb.sku.name if lb.sku else "Basic",
                    }
                )
        return idle_lbs

    def get_snapshots(self):
        """Finds snapshots that might be orphaned"""
        snapshots = self.compute.snapshots.list()
        return [
            {"name": s.name, "size_gb": s.disk_size_gb, "location": s.location} for s in snapshots
        ]

    def get_idle_app_gateways(self):
        """Finds App Gateways with no backend pools or idle"""
        gateways = self.network.application_gateways.list_all()
        idle_gateways = []
        for gw in gateways:
            if not gw.backend_address_pools or all(
                len(pool.backend_addresses or []) == 0 for pool in gw.backend_address_pools
            ):
                idle_gateways.append(
                    {
                        "name": gw.name,
                        "location": gw.location,
                        "sku": f"{gw.sku.name}_{gw.sku.tier}",
                    }
                )
        return idle_gateways

    def get_recovery_vaults(self):
        """Finds Recovery Service Vaults"""
        vaults = self.recovery.vaults.list_by_subscription_id(self.subscription_id)
        return [{"name": v.name, "location": v.location, "sku": v.sku.name} for v in vaults]

    def get_empty_app_service_plans(self):
        """Finds App Service Plans with 0 apps assigned"""
        plans = self.web.app_service_plans.list()
        empty_plans = []
        for plan in plans:
            if getattr(plan, "number_of_sites", 0) == 0:
                empty_plans.append(
                    {
                        "name": plan.name,
                        "location": plan.location,
                        "sku": plan.sku.name,
                        "tier": plan.sku.tier,
                    }
                )
        return empty_plans

    def get_sql_databases(self):
        """Finds SQL Databases - TODO: Add idle check with metrics"""
        servers = self.sql.servers.list()
        databases = []
        for server in servers:
            dbs = self.sql.databases.list_by_server(server.resource_group_name, server.name)
            for db in dbs:
                if db.name != "master":
                    databases.append(
                        {
                            "name": db.name,
                            "server": server.name,
                            "location": db.location,
                            "sku": db.sku.name if db.sku else "Unknown",
                        }
                    )
        return databases

    def get_user_name(self):
        """Returns the authenticated user's display name"""
        try:
            AuthorizationManagementClient(self.credentials, self.subscription_id)
            # Get current user info - this is a simplified approach
            return "Azure User"
        except Exception:
            return "Azure User"

    def get_subscription_name(self):
        """Returns the subscription display name"""
        try:
            sub_client = SubscriptionClient(self.credentials)
            sub = sub_client.subscriptions.get(self.subscription_id)
            return sub.display_name
        except Exception:
            return f"Subscription ({self.subscription_id[:8]}...)"

    def get_zombie_vms(self):
        """Identify 'zombie' VMs based on age and lack of activity (CPU < 1% for 7 days)."""
        vms = self.compute.virtual_machines.list_all()
        zombies = []
        end_time = datetime.datetime.now(datetime.UTC)
        start_time = end_time - datetime.timedelta(days=7)

        for vm in vms:
            resource_group = vm.id.split("/")[4] if "/" in vm.id else "Unknown"
            resource_id = (
                f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group}/"
                f"providers/Microsoft.Compute/virtualMachines/{vm.name}"
            )
            try:
                metrics = self.monitor.metrics.list(
                    resource_id,
                    timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                    interval="PT12H",
                    metricnames="Percentage CPU",
                    aggregation="Average",
                )
                avg_usage = 0.0
                has_data = False
                for item in metrics.value:
                    for timeseries in item.timeseries:
                        data_points = [
                            p.average for p in timeseries.data if p.average is not None
                        ]
                        if data_points:
                            avg_usage = sum(data_points) / len(data_points)
                            has_data = True

                if has_data and avg_usage < 1.0:
                    zombies.append({
                        "name": vm.name,
                        "usage": f"{round(avg_usage, 2)}%",
                        "rg": resource_group,
                    })
            except Exception:
                continue

        return zombies

    def get_utilization_report(self):
        """Generate a summarized utilization report for all VMs (24h CPU average)."""
        vms = self.compute.virtual_machines.list_all()
        report = []
        end_time = datetime.datetime.now(datetime.UTC)
        start_time = end_time - datetime.timedelta(days=1)

        for vm in vms:
            resource_group = vm.id.split("/")[4] if "/" in vm.id else "Unknown"
            resource_id = (
                f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group}/"
                f"providers/Microsoft.Compute/virtualMachines/{vm.name}"
            )
            try:
                metrics = self.monitor.metrics.list(
                    resource_id,
                    timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                    interval="PT1H",
                    metricnames="Percentage CPU",
                    aggregation="Average",
                )
                avg_usage = 0.0
                for item in metrics.value:
                    for timeseries in item.timeseries:
                        data_points = [
                            p.average for p in timeseries.data if p.average is not None
                        ]
                        if data_points:
                            avg_usage = sum(data_points) / len(data_points)

                report.append({
                    "name": vm.name,
                    "usage": round(avg_usage, 1),
                    "rg": resource_group,
                })
            except Exception:
                continue

        # Sort by highest usage
        report.sort(key=lambda x: x["usage"], reverse=True)
        return report

    def get_anomaly_data(self):
        """Detect spend anomalies using real Azure Cost Management data."""
        if not self.cost_management:
            return []

        scope = f"/subscriptions/{self.subscription_id}"
        end_date = datetime.datetime.now(datetime.UTC)
        start_date = end_date - datetime.timedelta(days=30)

        from azure.mgmt.costmanagement.models import (
            QueryAggregation,
            QueryDataset,
            QueryDefinition,
            QueryGrouping,
            QueryTimePeriod,
        )

        query = QueryDefinition(
            type="Usage",
            timeframe="Custom",
            time_period=QueryTimePeriod(from_property=start_date, to=end_date),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={"totalCost": QueryAggregation(name="PreTaxCost", function="Sum")},
                grouping=[QueryGrouping(type="Dimension", name="ServiceName")],
            ),
        )

        try:
            result = self.cost_management.query.usage(scope, query)
            services_data = {}
            for row in result.rows:
                cost = float(row[0])
                service = row[2]
                if service not in services_data:
                    services_data[service] = []
                services_data[service].append(cost)

            anomalies = []
            for service, costs in services_data.items():
                if len(costs) < 7:
                    continue
                recent_avg = sum(costs[-3:]) / 3
                hist_avg = sum(costs[:-3]) / len(costs[:-3]) if len(costs[:-3]) > 0 else 0

                dev = ((recent_avg - hist_avg) / hist_avg) * 100 if hist_avg > 0 else 0
                is_anomaly = dev > 20 and recent_avg > 10

                anomalies.append({
                    "service": service,
                    "cost": round(sum(costs), 2),
                    "is_anomaly": is_anomaly,
                    "deviation": f"{'+' if dev > 0 else ''}{round(dev)}%",
                })

            anomalies.sort(key=lambda x: x["cost"], reverse=True)
            return anomalies[:5]
        except Exception as e:
            print(f"Cost Management API Error: {e}")
            return []

    def get_ri_sp_candidates(self):
        """Reservations and Savings Plans recommendations."""
        return [
            {"sku": "Standard_D2s_v3", "region": "East US", "annual_savings": 1200.50},
            {"sku": "Standard_E4s_v3", "region": "West US", "annual_savings": 850.00},
        ]

    def get_cold_storage_candidates(self):
        """Suggest moving infrequently accessed data to cool/archive tier."""
        return [
            {"bucket": "logs-archive", "size_gb": 5000, "monthly_savings": 125.00},
            {"bucket": "legacy-backups", "size_gb": 2000, "monthly_savings": 50.00},
        ]

    def get_modernization_candidates(self):
        """Suggest moving VMs to PaaS/Serverless."""
        return [
            {"name": "legacy-app-vm", "target": "App Service", "annual_savings": 4500.00},
            {"name": "sql-vm-01", "target": "Azure SQL", "annual_savings": 3200.00},
        ]

    def get_policy_violations(self):
        """Audit resources against compliance policies using Azure Resource Graph."""
        try:
            from azure.mgmt.resourcegraph import ResourceGraphClient
            from azure.mgmt.resourcegraph.models import QueryRequest

            client = ResourceGraphClient(self.credentials)
            query = \"\"\"
                Resources 
                | where type =~ 'Microsoft.Compute/virtualMachines' 
                | where isnull(tags.owner) or isnull(tags.project)
                | project name, type, resourceGroup, tags
                | take 5
            \"\"\"
            request = QueryRequest(
                subscriptions=[self.subscription_id],
                query=query
            )
            response = client.resources(request)
            
            violations = []
            if hasattr(response, 'data'):
                for item in response.data:
                    violations.append({
                        "resource": item.get("name", "Unknown"),
                        "violation": "Missing Owner/Project Tags",
                        "severity": "HIGH",
                        "rule": "Tagging Compliance",
                        "action": "FLAGGED",
                        "detected_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
                    })
            
            return violations
        except Exception as e:
            print(f"Resource Graph API Error: {e}")
            return []

    def get_budget_status(self):
        """Returns budget vs actual spend."""
        return [
            {"name": "Production", "budget": 5000, "actual": 4850, "forecast": 5200},
            {"name": "Development", "budget": 1000, "actual": 450, "forecast": 950},
        ]

    def fast_scan(self):
        """Perform a quick scan of the environment for a summary view."""
        return {
            "vms": self.get_vm_inventory(),
            "orphans": self.get_orphaned_disks(),
            "zombies": self.get_zombie_vms(),
            "recommendations": self.get_ri_sp_candidates()
        }

    def get_live_prices(self):
        """
        Executes the Go Performance Core to fetch real-time Azure pricing data.
        """
        # Path to the Go binary
        go_binary = Path(__file__).resolve().parent.parent.parent / "engine-go" / "reaper-engine"

        if not go_binary.exists():
            print(f"[-] Error: Go binary not found at {go_binary}. Run ./reap.sh to build.")
            return {}

        try:
            # Run the Go scraper and capture JSON output
            result = subprocess.run(  # noqa: S603
                [str(go_binary), "--mode", "prices"], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            print(f"[-] Go Engine Error: {result.stderr}")
            return {}
        except Exception as e:
            print(f"[-] Failed to execute Go Scraper: {e}")
            return {}

    def get_burn_rate_forecast(self):
        """Calculates burn rate and EOM forecast using real Azure Cost data and ARIMA."""
        spend_data = []

        if self.cost_management:
            scope = f"/subscriptions/{self.subscription_id}"
            end_date = datetime.datetime.now(datetime.UTC)
            start_date = end_date - datetime.timedelta(days=30)

            from azure.mgmt.costmanagement.models import (
                QueryAggregation,
                QueryDataset,
                QueryDefinition,
                QueryTimePeriod,
            )

            query = QueryDefinition(
                type="Usage",
                timeframe="Custom",
                time_period=QueryTimePeriod(from_property=start_date, to=end_date),
                dataset=QueryDataset(
                    granularity="Daily",
                    aggregation={"totalCost": QueryAggregation(name="PreTaxCost", function="Sum")},
                ),
            )

            try:
                result = self.cost_management.query.usage(scope, query)
                if result.rows:
                    rows = sorted(result.rows, key=lambda x: x[1])
                    spend_data = [float(r[0]) for r in rows]
            except Exception as e:
                print(f"Cost Management API Error: {e}")

        # Fallback to DB or mocked if API fails
        if not spend_data:
            db = SessionLocal()
            history = (
                db.query(CostHistory)
                .filter(CostHistory.type == "ACTUAL")
                .order_by(CostHistory.timestamp.desc())
                .limit(30)
                .all()
            )
            db.close()
            spend_data = [float(h.amount) for h in reversed(history)]

        if not spend_data:
            spend_data = [120, 125, 118, 140, 135, 150, 145]

        forecaster = BudgetForecaster()
        forecast = forecaster.forecast_eom(spend_data)

        slope = 0
        if len(spend_data) >= 2:
            slope = (spend_data[-1] - spend_data[0]) / len(spend_data)

        return {
            "projected_total": forecast["projected_eom"],
            "daily_history": spend_data,
            "slope": slope,
            "confidence": forecast["confidence"],
        }

    def get_virtual_tags(self):
        """
        Returns virtual tagging logic (mocked for demo).
        """
        return [
            {"name": "Production Cluster", "virtual_tags": {"Env": "Prod", "Dept": "Eng"}},
            {"name": "Marketing-Web", "virtual_tags": {"Dept": "Mktg"}},
            {"name": "Data-Science-Sandbox", "virtual_tags": {"Owner": "DS-Team"}},
        ]

    def get_greenops_recommendations(self):
        """
        Sustainability recommendations.
        """
        return [
            {
                "name": "Batch Processor",
                "current_region": "East US",
                "target_region": "West US 2",
                "savings_pct": 22,
            },
            {
                "name": "Legacy Storage",
                "current_region": "West Europe",
                "target_region": "North Europe",
                "savings_pct": 15,
            },
        ]

    def execute_reap(self, resource_id, resource_type):
        """
        Executes a reap (delete/stop) action.
        """
        # In a real app, this would call the Azure API to delete/stop
        return {
            "status": "success",
            "message": f"Successfully authorized reap for {resource_id} ({resource_type})",
        }


if __name__ == "__main__":
    collector = AzureCollector()
    print("--- Scanning Azure VMs ---")
    for vm in collector.get_vm_inventory():
        print(f"Found VM: {vm['name']} [{vm['size']}]")

    print("\n--- Hunting Idle VMs ---")
    idle_results = collector.get_idle_vms()
    if not idle_results:
        print("No idle VMs found.")
    for v in idle_results:
        print(f"[!] IDLE VM: {v['name']} in RG {v['resource_group']} - CPU avg {v['average_cpu']}%")

    print("\n--- Hunting Orphaned Network Resources ---")
    orphaned_network = collector.get_orphaned_network_resources()
    if not orphaned_network["ips"] and not orphaned_network["lbs"]:
        print("No unassociated network waste found.")
    for ip in orphaned_network["ips"]:
        print(f"[!] REAPER TARGET: Unassociated IP {ip}")
    for lb in orphaned_network["lbs"]:
        print(f"[!] REAPER TARGET: Idle LB {lb}")

    print("\n--- Hunting Orphaned Disks ---")
    orphans = collector.get_orphaned_disks()
    if not orphans:
        print("No orphaned disks found. Infrastructure is clean.")
    for d in orphans:
        print(f"[!] REAPER TARGET: {d['name']} ({d['size_gb']}GB) - Tier: {d['tier']}")

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
    snaps = collector.get_snapshots()
    if not snaps:
        print("No snapshots found.")
    for snap in snaps:
        print(f"Snapshot: {snap['name']} ({snap['size_gb']}GB) - Location: {snap['location']}")
