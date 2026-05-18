import logging

import requests


class AWSPriceClient:
    URLS = {
        "EC2": "https://ec2instances.info/instances.json",
        "RDS": "https://instances.vantage.sh/rds/instances.json",
        "ElastiCache": "https://instances.vantage.sh/cache/instances.json",
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_live_prices(self):
        """
        Fetches live AWS pricing from the Vantage community datasets for all EC2, RDS, and ElastiCache components.
        """
        prices = []

        try:
            # 1. Fetch ALL EC2
            ec2_data = self._fetch_json(self.URLS["EC2"])
            for item in ec2_data:
                inst_type = item.get("instance_type", "")
                pricing = item.get("pricing", {})
                for region, reg_pricing in pricing.items():
                    ondemand = reg_pricing.get("linux", {}).get("ondemand")
                    if ondemand is not None:
                        prices.append(
                            self._build_price(inst_type, "Virtual Machines", region, ondemand)
                        )

            # 2. Fetch ALL RDS
            rds_data = self._fetch_json(self.URLS["RDS"])
            for item in rds_data:
                inst_type = item.get("instance_type", "")
                pricing = item.get("pricing", {})
                for region, reg_pricing in pricing.items():
                    # Prefer PostgreSQL, fallback to MySQL
                    ondemand = reg_pricing.get("PostgreSQL", {}).get("ondemand") or reg_pricing.get(
                        "MySQL", {}
                    ).get("ondemand")
                    if ondemand is not None:
                        prices.append(
                            self._build_price(inst_type, "SQL Database", region, ondemand)
                        )

            # 3. Fetch ALL ElastiCache
            cache_data = self._fetch_json(self.URLS["ElastiCache"])
            for item in cache_data:
                inst_type = item.get("instance_type", "")
                pricing = item.get("pricing", {})
                for region, reg_pricing in pricing.items():
                    ondemand = reg_pricing.get("Redis", {}).get("ondemand") or reg_pricing.get(
                        "Memcached", {}
                    ).get("ondemand")
                    if ondemand is not None:
                        prices.append(
                            self._build_price(inst_type, "Azure Cache for Redis", region, ondemand)
                        )

        except Exception as e:
            self.logger.error(f"Error fetching AWS prices: {e}")

        return prices

    def _fetch_json(self, url):
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        response.raise_for_status()
        return response.json()

    def _build_price(self, sku, service_name, region, price_val):
        try:
            val = float(price_val)
        except ValueError:
            val = 0.0
        return {
            "armResourceName": sku,
            "skuName": sku,
            "serviceName": service_name,
            "armRegionName": region,
            "retailPrice": val,
            "unitOfMeasure": "1 Hour",
        }
