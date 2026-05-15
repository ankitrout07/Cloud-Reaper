import logging

from dotenv import load_dotenv

from reaper.collectors.azure_collector import AzureCollector

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
az = AzureCollector()
try:
    print(az.get_idle_vms())
except Exception:
    import traceback

    traceback.print_exc()
