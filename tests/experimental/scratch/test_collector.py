import os

from reaper.collectors.azure_collector import AzureCollector


def test_azure_collector_init():
    # Force set the subscription ID for this test
    os.environ["AZURE_SUBSCRIPTION_ID"] = "7ef42162-83d2-4247-8010-38bf34dd1453"

    az = AzureCollector()
    assert az.subscription_id == "7ef42162-83d2-4247-8010-38bf34dd1453"
    assert hasattr(az, "get_vm_inventory")
