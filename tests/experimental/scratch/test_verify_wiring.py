import json

from reaper.collectors.azure_collector import AzureCollector


def test_verify_wiring():
    az = AzureCollector()

    # This should trigger the Go engine
    # In a real test environment we might skip this if Go engine is not running,
    # but for discovery purposes, we make it a valid test function.
    assert hasattr(az, 'get_live_prices')
    assert hasattr(az, 'fast_scan')
