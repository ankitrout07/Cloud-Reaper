import logging
import requests

class GCPPriceClient:
    URL = "https://raw.githubusercontent.com/doitintl/gcpinstances.info/master/public/data/pricing.json"

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_live_prices(self):
        """
        Fetches live GCP Compute Engine pricing from the gcpinstances.info dataset for ALL regions and ALL instances.
        """
        try:
            response = requests.get(self.URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            response.raise_for_status()
            data = response.json()

            prices = []
            instances = data.get("instances", [])
            for inst in instances:
                name = inst.get("name", "")
                pricing = inst.get("pricing", {})
                
                for region, reg_pricing in pricing.items():
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
