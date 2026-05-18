import logging

import requests


class GCPPriceClient:
    URL = "https://raw.githubusercontent.com/doitintl/gcpinstances.info/master/public/data/pricing.json"

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_live_prices(self):
        """
        Fetches live GCP Compute Engine pricing from the gcpinstances.info dataset.
        """
        try:
            response = requests.get(self.URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            response.raise_for_status()
            data = response.json()

            prices = []
            # Curated popular regions
            target_regions = ["us-central1", "us-east1", "europe-west1", "asia-east1"]
            # Curated popular instance prefixes
            target_prefixes = ("e2-", "n1-", "n2-", "c2-", "m1-")

            instances = data.get("instances", [])
            for inst in instances:
                name = inst.get("name", "")
                if not name.startswith(target_prefixes):
                    continue

                pricing = inst.get("pricing", {})
                for region in target_regions:
                    reg_pricing = pricing.get(region, {})
                    ondemand = reg_pricing.get("linuxOnDemand")

                    if ondemand is not None:
                        try:
                            price_val = float(ondemand)
                            prices.append(
                                {
                                    "armResourceName": name,
                                    "skuName": name,
                                    "serviceName": "Compute Engine",
                                    "armRegionName": region,
                                    "retailPrice": price_val,
                                    "unitOfMeasure": "1 Hour",
                                }
                            )
                        except ValueError:
                            continue
            return prices
        except Exception as e:
            self.logger.error(f"Error fetching GCP prices: {e}")
            return []
