from __future__ import annotations

import logging
from typing import Any

import requests


class GCPPriceClient:
    URL = "https://raw.githubusercontent.com/doitintl/gcpinstances.info/master/public/data/pricing.json"

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._compute_index: dict[tuple[str, str], float] | None = None
        self._instance_specs: dict[str, dict[str, Any]] | None = None

    def get_live_prices(self):
        """
        Fetches live GCP Compute Engine pricing from the gcpinstances.info dataset for ALL regions and ALL instances.
        """
        try:
            return self._fetch_compute_prices()
        except Exception as e:
            self.logger.error(f"Error fetching GCP prices: {e}")
            return []

    def get_catalog_prices(self):
        """Fetch Compute Engine on-demand prices for the price catalog UI."""
        try:
            return self._fetch_compute_prices()
        except Exception as e:
            self.logger.error(f"Error fetching GCP catalog prices: {e}")
            return []

    def lookup_price(self, sku: str, region: str) -> float | None:
        """Resolve a single Compute Engine on-demand price without loading the full catalog."""
        index = self._get_compute_index()
        return index.get((sku.lower(), region))

    def _get_compute_index(self) -> dict[tuple[str, str], float]:
        if self._compute_index is None:
            response = requests.get(self.URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            data = response.json()
            index: dict[tuple[str, str], float] = {}
            for inst in data.get("instances", []):
                name = inst.get("name", "")
                for reg, reg_pricing in inst.get("pricing", {}).items():
                    ondemand = reg_pricing.get("linuxOnDemand")
                    if ondemand is not None:
                        try:
                            index[(name.lower(), reg)] = float(ondemand)
                        except ValueError:
                            continue
            self._compute_index = index
        return self._compute_index

    def _get_instance_specs(self) -> dict[str, dict[str, Any]]:
        """Fetch and cache instance specifications from GCP pricing data."""
        if self._instance_specs is None:
            response = requests.get(self.URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            data = response.json()
            specs: dict[str, dict[str, Any]] = {}
            for inst in data.get("instances", []):
                name = inst.get("name", "")
                specs[name] = {
                    "vcpu": inst.get("vcpu"),
                    "memory": inst.get("memory"),
                    "guestAccelerators": inst.get("guestAccelerators"),
                    "machineType": inst.get("machineType"),
                    "cpuPlatform": inst.get("cpuPlatform"),
                }
            self._instance_specs = specs
        return self._instance_specs

    def _fetch_compute_prices(self):
        index = self._get_compute_index()
        specs = self._get_instance_specs()
        return [
            {
                "armResourceName": sku,
                "skuName": sku,
                "serviceName": "Compute Engine",
                "armRegionName": region,
                "retailPrice": price_val,
                "unitOfMeasure": "1 Hour",
                **specs.get(sku, {}),
            }
            for (sku, region), price_val in index.items()
        ]
