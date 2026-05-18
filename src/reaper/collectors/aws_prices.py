import logging

import requests


class AWSPriceClient:
    URL = "https://ec2instances.info/instances.json"

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_live_prices(self):
        """
        Fetches live AWS EC2 pricing from the Vantage community dataset.
        """
        try:
            response = requests.get(self.URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            response.raise_for_status()
            data = response.json()

            prices = []
            # Curated popular regions to avoid rendering tens of thousands of rows
            target_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
            # Curated popular instance prefixes
            target_prefixes = ("t3.", "t2.", "m5.", "m6i.", "c5.", "c6i.", "r5.", "r6i.")

            for item in data:
                inst_type = item.get("instance_type", "")
                if not inst_type.startswith(target_prefixes):
                    continue

                pricing = item.get("pricing", {})
                for region in target_regions:
                    reg_pricing = pricing.get(region, {})
                    linux_pricing = reg_pricing.get("linux", {})
                    ondemand = linux_pricing.get("ondemand")

                    if ondemand:
                        try:
                            price_val = float(ondemand)
                            prices.append(
                                {
                                    "armResourceName": inst_type,
                                    "skuName": inst_type,
                                    "serviceName": "EC2",
                                    "armRegionName": region,
                                    "retailPrice": price_val,
                                    "unitOfMeasure": "1 Hour",
                                }
                            )
                        except ValueError:
                            continue
            return prices
        except Exception as e:
            self.logger.error(f"Error fetching AWS prices: {e}")
            return []
