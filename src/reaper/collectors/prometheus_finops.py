# src/reaper/collectors/prometheus_finops.py
import logging

import requests

logger = logging.getLogger("reaper.collector.prometheus")


class PrometheusFinOpsCollector:
    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self.api_endpoint = f"{prometheus_url}/api/v1/query"

    def fetch_node_avg_cpu_utilization(self, duration_window: str = "7d") -> dict:
        """Executes PromQL queries to calculate average CPU utilization across clusters."""
        # PromQL query tracking average non-idle CPU percentage across the fleet
        promql_query = f"100 - (avg by (instance) (rate(node_cpu_seconds_total{{mode='idle'}}[{duration_window}])) * 100)"

        try:
            response = requests.get(self.api_endpoint, params={"query": promql_query}, timeout=10)
            if response.status_code != 200:
                logger.error(f"Prometheus query failure. HTTP Status: {response.status_code}")
                return {}

            results = response.json().get("data", {}).get("result", [])
            utilization_map = {}
            for item in results:
                instance = item.get("metric", {}).get("instance", "unknown")
                # Extract the final scalar metric reading tuple [timestamp, value]
                value = float(item.get("value", [0, 0])[1])
                utilization_map[instance] = round(value, 2)

            return utilization_map
        except Exception as e:
            logger.critical(f"Failed to reach Prometheus API backend: {e!s}")
            return {}
