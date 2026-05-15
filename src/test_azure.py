from reaper.collectors.azure_collector import AzureCollector
import os
import logging
logging.basicConfig(level=logging.DEBUG)
os.environ["AZURE_SUBSCRIPTION_ID"] = "dummy"
az = AzureCollector()
try:
    print(az.get_idle_vms())
except Exception as e:
    print("ERROR:", e)
