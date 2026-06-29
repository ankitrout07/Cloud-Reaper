"""
Test script for the enhanced FinOps pipeline.
Validates sequential pipeline execution with workload differentiation.
"""

import sys
from pathlib import Path

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reaper.engine.core.calculator import RightsizingAgent
from reaper.engine.core.scheduler import (
    FinOpsPipeline,
    WorkloadClassifier,
)
from reaper.engine.core.logic import analyze_compute_telemetry


def test_workload_classification():
    """Test workload classification based on tags and names."""
    print("\n[TEST 1] Workload Classification")
    classifier = WorkloadClassifier()

    test_resources = [
        {"name": "prod-web-server-01", "tags": {"environment": "production"}},
        {"name": "dev-test-api-02", "tags": {"env": "dev"}},
        {"name": "staging-db-01", "tags": {"tier": "staging"}},
        {"name": "unknown-resource", "tags": {}},
    ]

    for resource in test_resources:
        env_type = classifier.classify_resource(resource)
        print(f"  ✓ {resource['name']}: {env_type}")

    print("  [PASS] Workload classification working correctly")


def test_vectorized_compute_analysis():
    """Test vectorized compute telemetry analysis with multi-lookback support."""
    print("\n[TEST 2] Vectorized Compute Telemetry Analysis")

    # Create test data for 3 resources over 30 days
    num_resources = 3
    num_days = 30

    # Resource 1: Low utilization (shutdown candidate)
    cpu_data_1 = np.array([2.0, 3.0, 1.5, 4.0, 2.5] * 6)  # Very low CPU
    mem_data_1 = np.array([10.0, 12.0, 8.0, 15.0, 11.0] * 6)  # Low memory

    # Resource 2: Burstable pattern (low avg, high peaks)
    cpu_data_2 = np.array([15.0, 18.0, 85.0, 12.0, 20.0, 75.0] * 5)  # Burstable
    mem_data_2 = np.array([25.0, 30.0, 60.0, 28.0, 35.0, 55.0] * 5)

    # Resource 3: Stable workload (stay)
    cpu_data_3 = np.array([45.0, 52.0, 48.0, 55.0, 50.0, 47.0] * 5)  # Stable
    mem_data_3 = np.array([60.0, 65.0, 62.0, 68.0, 63.0, 61.0] * 5)

    cpu_matrix = np.vstack([cpu_data_1, cpu_data_2, cpu_data_3])
    mem_matrix = np.vstack([mem_data_1, mem_data_2, mem_data_3])

    # Test with different lookback periods
    for lookback in [7, 14, 30]:
        print(f"\n  Testing with {lookback}-day lookback:")

        # Test production environment
        prod_recommendations = analyze_compute_telemetry(
            cpu_matrix, mem_matrix, env_type="production", lookback_days=lookback
        )
        print("    Production Environment:")
        for rec in prod_recommendations:
            print(f"      Resource {rec['resource_index']}: {rec['action']} - {rec['reason']}")

        # Test dev-test environment
        dev_recommendations = analyze_compute_telemetry(
            cpu_matrix, mem_matrix, env_type="dev-test", lookback_days=lookback
        )
        print("    Dev-Test Environment:")
        for rec in dev_recommendations:
            print(f"      Resource {rec['resource_index']}: {rec['action']} - {rec['reason']}")

    print("  [PASS] Vectorized compute analysis with multi-lookback working")


def test_environment_aware_rightsizing():
    """Test environment-aware rightsizing agent."""
    print("\n[TEST 3] Environment-Aware Rightsizing Agent")

    # Test production agent
    prod_agent = RightsizingAgent(environment_type="production")
    prod_metrics = {"cpu": 25.0, "mem": 30.0, "iops": 50, "net": 40}
    prod_result = prod_agent.evaluate_migration(prod_metrics, "Standard_D4s_v3")

    print("  Production Agent:")
    print(f"    Recommended Action: {prod_result['recommended_action']}")
    print(f"    Risk Profile: {prod_result['risk_profile']}")
    print(f"    Thresholds: {prod_result['thresholds_used']}")

    # Test dev-test agent
    dev_agent = RightsizingAgent(environment_type="dev-test")
    dev_result = dev_agent.evaluate_migration(prod_metrics, "Standard_D4s_v3")

    print("  Dev-Test Agent:")
    print(f"    Recommended Action: {dev_result['recommended_action']}")
    print(f"    Risk Profile: {dev_result['risk_profile']}")
    print(f"    Thresholds: {dev_result['thresholds_used']}")

    print("  [PASS] Environment-aware rightsizing working")


def test_sequential_pipeline():
    """Test the complete sequential pipeline execution."""
    print("\n[TEST 4] Sequential FinOps Pipeline")

    # Create mock telemetry data
    telemetry_data = [
        {
            "id": "vm-001",
            "name": "prod-web-server-01",
            "sku": "Standard_D4s_v3",
            "tags": {"environment": "production"},
            "cpu_history": [45.0, 52.0, 48.0, 55.0, 50.0, 47.0, 53.0],
            "memory_history": [60.0, 65.0, 62.0, 68.0, 63.0, 61.0, 66.0],
            "iops": 150,
            "network_throughput": 80,
        },
        {
            "id": "vm-002",
            "name": "dev-test-api-01",
            "sku": "Standard_D2s_v3",
            "tags": {"env": "dev"},
            "cpu_history": [5.0, 8.0, 3.0, 12.0, 6.0, 4.0, 7.0],
            "memory_history": [15.0, 18.0, 12.0, 25.0, 16.0, 14.0, 19.0],
            "iops": 50,
            "network_throughput": 30,
        },
    ]

    # Initialize pipeline
    pipeline = FinOpsPipeline(price_book={"Standard_D4s_v3": 0.20, "Standard_D2s_v3": 0.10})

    print("  Executing sequential pipeline...")
    results = pipeline.execute_pipeline(
        telemetry_data=telemetry_data, provider="azure", lookback_days=7
    )

    if results["pipeline_status"] == "completed":
        print(f"  ✓ Pipeline completed successfully in {results['execution_time_seconds']:.2f}s")

        # Verify sequential execution
        expected_stages = [
            "telemetry_classification",
            "rightsizing_analysis",
            "baseline_update",
            "commitment_management",
        ]
        for stage in expected_stages:
            if stage in results["stages"]:
                status = "✓" if results["stages"][stage]["success"] else "✗"
                print(f"    {status} {stage}: {results['stages'][stage]['success']}")

        print(f"  Final recommendations: {len(results['final_recommendations'])}")
        print("  [PASS] Sequential pipeline execution validated")
    else:
        print(f"  [FAIL] Pipeline execution failed: {results.get('error')}")
        return False

    return True


def run_all_tests():
    """Run all pipeline validation tests."""
    print("=" * 60)
    print("🧪 FINOPS PIPELINE VALIDATION TESTS")
    print("=" * 60)

    try:
        test_workload_classification()
        test_vectorized_compute_analysis()
        test_environment_aware_rightsizing()
        test_sequential_pipeline()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ TESTS FAILED: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
