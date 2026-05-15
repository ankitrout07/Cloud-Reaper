from reaper.collectors.azure_collector import AzureCollector
from azure.identity import DefaultAzureCredential
import os
import logging
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.DEBUG)
az = AzureCollector()
try:
    print(az.get_idle_vms())
except Exception as e:
    import traceback
    traceback.print_exc()
