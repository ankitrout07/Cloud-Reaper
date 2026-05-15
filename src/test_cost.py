from reaper.collectors.azure_collector import AzureCollector
import os
from dotenv import load_dotenv
load_dotenv()
az = AzureCollector()
try:
    print(az.get_service_bucket_spend())
except Exception as e:
    print("ERROR:", e)
