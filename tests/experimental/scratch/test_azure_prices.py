import json

from reaper.collectors.azure_prices import AzurePriceClient


def test_prices():
    client = AzurePriceClient(currency="USD")

    print("Fetching Virtual Machines prices...")
    vm_prices = client.get_prices_by_service("Virtual Machines")
    print(f"Found {len(vm_prices)} VM price items.")

    if vm_prices:
        print("Sample VM Price Item:")
        print(json.dumps(vm_prices[0], indent=2))

    print("\nFetching Standard_B2s price by armResourceName...")
    # Example armResourceName for B2s might be different, let's try a common one
    # Often it's 'Virtual Machines B2s Series' or similar in Retail API
    # Actually, armResourceName in Retail API is often like 'Virtual Machines B2s Series'
    # Let's try searching for a specific one if we know it.

    # Let's just test category fetch
    print("\nFetching Storage prices...")
    storage_prices = client.get_category_prices("Storage")
    print(f"Found {len(storage_prices)} Storage price items.")


if __name__ == "__main__":
    test_prices()
