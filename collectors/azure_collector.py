import os
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class AzureCollector:
    def __init__(self):
        self.subscription_id = os.getenv('AZURE_SUBSCRIPTION_ID')
        self.credentials = DefaultAzureCredential()
        # Only initialize client if subscription_id exists to avoid immediate crash
        if self.subscription_id:
            self.compute_client = ComputeManagementClient(self.credentials, self.subscription_id)
            self.monitor_client = MonitorManagementClient(self.credentials, self.subscription_id)
        else:
            self.compute_client = None
            self.monitor_client = None

    def get_vm_inventory(self):
        if not self.compute_client: return []
        try:
            vms = self.compute_client.virtual_machines.list_all()
            return [{'name': vm.name, 'size': vm.hardware_profile.vm_size} for vm in vms]
        except Exception:
            return []

    def _extract_rg(self, resource_id):
        # Azure IDs follow: /subscriptions/.../resourceGroups/{RG_NAME}/...
        parts = resource_id.split('/')
        if len(parts) > 4:
            return parts[4]
        return "N/A"

    def get_orphaned_disks(self):
        if not self.compute_client: return []
        try:
            disks = self.compute_client.disks.list()
            return [{
                'name': d.name, 
                'size_gb': d.disk_size_gb,
                'rg': self._extract_rg(d.id)
            } for d in disks if d.managed_by is None]
        except Exception:
            return []

    def get_idle_vms(self, cpu_threshold=5.0):
        """
        Returns VMs with average CPU usage below the threshold over the last hour.
        """
        if not self.compute_client or not self.monitor_client: return []
        
        idle_vms = []
        try:
            vms = self.compute_client.virtual_machines.list_all()
            for vm in vms:
                # Construct resource ID
                resource_id = vm.id
                
                # Query metrics for the last hour
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(hours=1)
                
                metrics = self.monitor_client.metrics.list(
                    resource_id,
                    timespan=f"{start_time.isoformat()}Z/{end_time.isoformat()}Z",
                    interval='PT1H',
                    metricnames='Percentage CPU',
                    aggregation='Average'
                )
                
                for item in metrics.value:
                    for timeseries in item.timeseries:
                        for data in timeseries.data:
                            if data.average is not None and data.average < cpu_threshold:
                                idle_vms.append({
                                    "name": vm.name,
                                    "usage": round(data.average, 2),
                                    "id": vm.id,
                                    "rg": self._extract_rg(vm.id)
                                })
            return idle_vms
        except Exception as e:
            print(f"Error fetching idle VMs: {e}")
            return []

    def _calculate_avg(self, metric_item):
        avgs = []
        for timeseries in metric_item.timeseries:
            avgs.extend([d.average for d in timeseries.data if d.average is not None])
        return sum(avgs) / len(avgs) if avgs else 0

    def _calculate_max(self, metric_item):
        maxs = []
        for timeseries in metric_item.timeseries:
            maxs.extend([d.maximum for d in timeseries.data if d.maximum is not None])
        return max(maxs) if maxs else 0

    def _determine_status(self, avg_cpu, peak_ram):
        if avg_cpu < 10:
            return "UNDER-UTILIZED", "Downgrade SKU", "text-yellow-400"
        elif avg_cpu > 80:
            return "OVER-UTILIZED", "Upgrade SKU (Performance Risk)", "text-red-500"
        else:
            return "OPTIMIZED", "Maintain", "text-green-400"

    def get_utilization_report(self):
        if not self.compute_client or not self.monitor_client: return []
        report = []
        try:
            vms = self.compute_client.virtual_machines.list_all()
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            for vm in vms:
                resource_id = vm.id
                metrics = self.monitor_client.metrics.list(
                    resource_id,
                    timespan=f"{start_time.isoformat()}Z/{end_time.isoformat()}Z",
                    interval='P1D',
                    metricnames='Percentage CPU,Available Memory Bytes',
                    aggregation='Average,Maximum'
                )
                cpu_avg, ram_peak = 0, 0
                for item in metrics.value:
                    if item.name.value == 'Percentage CPU':
                        cpu_avg = self._calculate_avg(item)
                    elif item.name.value == 'Available Memory Bytes':
                        ram_peak = self._calculate_max(item)
                status, rec, color = self._determine_status(cpu_avg, ram_peak)
                report.append({
                    "name": vm.name,
                    "rg": self._extract_rg(vm.id),
                    "current_sku": vm.hardware_profile.vm_size,
                    "metrics": f"CPU: {cpu_avg:.1f}% | RAM Avail (Peak): {ram_peak / (1024**3):.1f} GB",
                    "status": status,
                    "recommendation": rec,
                    "color": color
                })
            return report
        except Exception as e:
            print(f"Error generating utilization report: {e}")
            return []


