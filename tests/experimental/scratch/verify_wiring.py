import json

from collectors.azure_collector import AzureCollector


def verify_wiring():
    print("Checking AzureCollector -> Go Engine -> Retail API wiring...")
    az = AzureCollector()

    # This should trigger the Go engine
    prices = az.get_live_prices()

    print(f"Result: Found {len(prices)} price items.")
    if len(prices) > 0:
        print("Wiring is CORRECT. Sample SKU:", prices[0].get("armResourceName"))
    else:
        print("Wiring issue: No prices returned. Check Go engine output.")
        # Print the full scan result to debug
        print("Full Scan Result:", json.dumps(az.fast_scan(), indent=2)[:500] + "...")


if __name__ == "__main__":
    verify_wiring()
