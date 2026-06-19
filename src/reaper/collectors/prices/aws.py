from __future__ import annotations

import logging
from typing import ClassVar

import requests


class AWSPriceClient:
    URLS: ClassVar[dict[str, str]] = {
        "EC2": "https://ec2instances.info/instances.json",
        "RDS": "https://instances.vantage.sh/rds/instances.json",
        "ElastiCache": "https://instances.vantage.sh/cache/instances.json",
    }
    URL: ClassVar[str] = URLS["EC2"]

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._ec2_index: dict[tuple[str, str], float] | None = None

    def get_live_prices(self):
        """
        Fetches live AWS pricing from the Vantage community datasets for all EC2, RDS, and ElastiCache components.
        """
        prices = []

        try:
            prices.extend(self._fetch_ec2_prices())
            prices.extend(self._fetch_rds_prices())
            prices.extend(self._fetch_elasticache_prices())
        except Exception as e:
            self.logger.error(f"Error fetching AWS prices: {e}")

        return prices

    def get_catalog_prices(self):
        """Fetch EC2 on-demand prices for the price catalog UI."""
        try:
            return self._fetch_ec2_prices()
        except Exception as e:
            self.logger.error(f"Error fetching AWS catalog prices: {e}")
            return []

    def _fetch_ec2_prices(self):
        prices = []
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
        return prices

    def _fetch_rds_prices(self):
        prices = []
        rds_data = self._fetch_json(self.URLS["RDS"])
        for item in rds_data:
            inst_type = item.get("instance_type", "")
            pricing = item.get("pricing", {})
            for region, reg_pricing in pricing.items():
                ondemand = reg_pricing.get("PostgreSQL", {}).get("ondemand") or reg_pricing.get(
                    "MySQL", {}
                ).get("ondemand")
                if ondemand is not None:
                    prices.append(self._build_price(inst_type, "SQL Database", region, ondemand))
        return prices

    def _fetch_elasticache_prices(self):
        prices = []
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
        return prices

    def lookup_price(self, sku: str, region: str) -> float | None:
        """Resolve a single EC2 on-demand Linux price without loading the full catalog."""
        index = self._get_ec2_index()
        return index.get((sku.lower(), region))

    def _get_ec2_index(self) -> dict[tuple[str, str], float]:
        if self._ec2_index is None:
            index: dict[tuple[str, str], float] = {}
            for item in self._fetch_json(self.URLS["EC2"]):
                inst_type = item.get("instance_type", "")
                for reg, reg_pricing in item.get("pricing", {}).items():
                    ondemand = reg_pricing.get("linux", {}).get("ondemand")
                    if ondemand is not None:
                        try:
                            index[(inst_type.lower(), reg)] = float(ondemand)
                        except ValueError:
                            continue
            self._ec2_index = index
        return self._ec2_index

    def _fetch_json(self, url):
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
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
