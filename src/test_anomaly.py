from dotenv import load_dotenv

from reaper.collectors.azure_collector import AzureCollector

load_dotenv()
az = AzureCollector()
try:
    print(az.get_anomaly_data())
except Exception as e:
    print("ERROR:", e)
