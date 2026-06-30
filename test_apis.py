import logging
import sys

logging.basicConfig(level=logging.ERROR)

# Setup path so it finds reaper
sys.path.insert(0, "./src")

from reaper.collectors.prices.aws import AWSPriceClient
from reaper.collectors.prices.azure import AzurePriceClient
from reaper.collectors.prices.gcp import GCPPriceClient


def test():
    print("Testing AWS...")
    try:
        aws = AWSPriceClient()
        prices = aws.get_catalog_prices()
        print(f"AWS returned {len(prices)} prices. First: {prices[0] if prices else 'None'}")
    except Exception as e:
        print(f"AWS Failed: {e}")

    print("\nTesting Azure...")
    try:
        azure = AzurePriceClient()
        prices = azure.get_catalog_prices()
        print(f"Azure returned {len(prices)} prices. First: {prices[0] if prices else 'None'}")
    except Exception as e:
        print(f"Azure Failed: {e}")

    print("\nTesting GCP...")
    try:
        gcp = GCPPriceClient()
        prices = gcp.get_catalog_prices()
        print(f"GCP returned {len(prices)} prices. First: {prices[0] if prices else 'None'}")
    except Exception as e:
        print(f"GCP Failed: {e}")


if __name__ == "__main__":
    test()
