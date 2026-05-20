# src/reaper/engine/metrics_analyzer.py
from reaper.collectors.prometheus_finops import PrometheusFinOpsCollector

class FinOpsTelemetryAnalyzer:
    def __init__(self, prometheus_url: str):
        self.prom_collector = PrometheusFinOpsCollector(prometheus_url)

    def analyze_compute_waste_index(self, active_inventory: list) -> list:
        """Cross-references Prometheus utilization data against actual asset cost metrics."""
        cpu_metrics = self.prom_collector.fetch_node_avg_cpu_utilization()
        optimization_insights = []

        for asset in active_inventory:
            instance_ip = asset.get("private_ip")
            monthly_cost = asset.get("monthly_cost", 0.0)
            
            # Match inventory assets with active Prometheus telemetry instances
            matching_instance = next((inst for inst in cpu_metrics if instance_ip and inst and instance_ip in inst), None)
            avg_utilization = cpu_metrics.get(matching_instance, 50.0) if matching_instance else 50.0

            # Underutilization threshold rule: Flag instances running under 10% capacity
            if avg_utilization < 10.0:
                potential_savings = monthly_cost * 0.50 # Target a baseline 50% scale-down downsize
                insight = {
                    "resource_id": asset.get("resource_id"),
                    "current_sku": asset.get("sku_size"),
                    "avg_cpu_utilization": f"{avg_utilization}%",
                    "monthly_waste_impact": f"${potential_savings:.2f}",
                    "remediation_action": "DOWNGRADE_SKU_FAMILY"
                }
                optimization_insights.append(insight)

        return optimization_insights
