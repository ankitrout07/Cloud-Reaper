import os
import sys
from dotenv import load_dotenv

# Force absolute path discovery
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("--- DEBUG: Script Started ---")

try:
    from collectors.aws_collector import AWSCollector
    from collectors.azure_collector import AzureCollector
    from engine.calculator import CostCalculator
    print("--- DEBUG: Imports Successful ---")
except Exception as e:
    print(f"--- DEBUG: Import Failed! Error: {e} ---")
    sys.exit(1)

load_dotenv()

def run_reaper():
    print("--- DEBUG: Entering run_reaper() ---")
    # ... rest of your code ...
    # (Ensure the print statements from the previous main.py are here)

if __name__ == "__main__":
    print("--- DEBUG: __main__ Triggered ---")
    run_reaper()
else:
    print("--- DEBUG: __main__ NOT Triggered ---")