# tests/unit/test_prometheus_telemetry.py
import unittest
from unittest.mock import MagicMock, patch

from reaper.collectors.prometheus_finops import PrometheusFinOpsCollector
from reaper.engine.metrics_analyzer import FinOpsTelemetryAnalyzer


class TestPrometheusTelemetry(unittest.TestCase):
    @patch("requests.get")
    def test_fetch_node_avg_cpu_utilization(self, mock_get):
        # Mock successful Prometheus response payload
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {"metric": {"instance": "10.0.1.4"}, "value": [1779285600, "8.5"]},
                    {"metric": {"instance": "10.0.1.5"}, "value": [1779285600, "50.2"]},
                ],
            },
        }
        mock_get.return_value = mock_response

        collector = PrometheusFinOpsCollector()
        cpu_metrics = collector.fetch_node_avg_cpu_utilization()

        self.assertEqual(cpu_metrics.get("10.0.1.4"), 8.5)
        self.assertEqual(cpu_metrics.get("10.0.1.5"), 50.2)

    @patch(
        "reaper.collectors.prometheus_finops.PrometheusFinOpsCollector.fetch_node_avg_cpu_utilization"
    )
    def test_analyze_compute_waste_index(self, mock_fetch):
        # Mock collector metric output
        mock_fetch.return_value = {"10.0.1.4": 8.5, "10.0.1.5": 50.2}

        active_inventory = [
            {
                "resource_id": "aks-worker-01",
                "private_ip": "10.0.1.4",
                "sku_size": "Standard_D4_v5",
                "monthly_cost": 140.0,
            },
            {
                "resource_id": "aks-worker-02",
                "private_ip": "10.0.1.5",
                "sku_size": "Standard_B2s",
                "monthly_cost": 30.0,
            },
        ]

        analyzer = FinOpsTelemetryAnalyzer("http://localhost:9090")
        insights = analyzer.analyze_compute_waste_index(active_inventory)

        # Should only flag aks-worker-01 (utilization < 10.0%)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["resource_id"], "aks-worker-01")
        self.assertEqual(insights[0]["avg_cpu_utilization"], "8.5%")
        self.assertEqual(insights[0]["monthly_waste_impact"], "$70.00")
        self.assertEqual(insights[0]["remediation_action"], "DOWNGRADE_SKU_FAMILY")
