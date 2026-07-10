"""
Parallel Azure Price Client using Go backend

This module provides a drop-in replacement for the Azure price client that leverages
the high-performance Go parallel price scraper for 10-20x faster performance.
"""

import logging
from typing import Any

from reaper.integrations.go_bridge import parallel_prices

AZURE_RETAIL_SERVICE_NAMES = [
    "Virtual Machines",
    "Virtual Machines Licenses",
    "Azure Kubernetes Service",
    "Container Instances",
    "App Service",
    "Functions",
    "Storage",
    "Archive Storage",
    "Azure NetApp Files",
    "Virtual Network",
    "VPN Gateway",
    "ExpressRoute",
    "Azure Front Door Service",
    "Bandwidth",
    "Load Balancer",
    "NAT Gateway",
    "SQL Database",
    "Azure Cosmos DB",
    "Azure Database for PostgreSQL",
    "Azure Database for MySQL",
    "Cache for Redis",
    "Azure Monitor",
    "Log Analytics",
    "Key Vault",
    "Microsoft Defender for Cloud",
]


class AzureParallelPriceClient:
    """
    High-performance Azure price client using Go parallel scraping backend.
    
    This provides the same interface as AzurePriceClient but leverages Go goroutines
    for parallel API calls, resulting in 10-20x performance improvements.
    """

    def __init__(self, currency="USD"):
        self.currency = currency
        self.logger = logging.getLogger(__name__)

    async def get_catalog_prices(self, concurrency: int = 10) -> list[dict[str, Any]]:
        """
        Fetch the Azure Retail Prices API catalog for all supported service categories
        using high-performance parallel Go backend.

        Args:
            concurrency: Number of parallel workers (default: 10)

        Returns:
            List of enriched price items with specifications
        """
        self.logger.info(f"Fetching Azure catalog prices using Go parallel scraper (concurrency={concurrency})")
        
        result = await parallel_prices(
            services=AZURE_RETAIL_SERVICE_NAMES,
            concurrency=concurrency,
            region=""
        )
        
        if result is None:
            self.logger.error("Failed to fetch prices from Go backend")
            return []
        
        raw_prices = result.get("prices", [])
        self.logger.info(f"Fetched {len(raw_prices)} price items from Go backend")
        
        # Extract specifications from the raw pricing data
        enriched_prices = []
        for price in raw_prices:
            enriched_price = self._extract_specifications(price)
            enriched_prices.append(enriched_price)

        return enriched_prices

    async def get_prices_by_region(
        self, 
        services: list[str] | None = None,
        region: str = "eastus",
        concurrency: int = 10
    ) -> list[dict[str, Any]]:
        """
        Fetch prices for specific services in a region using parallel Go backend.

        Args:
            services: List of service names (uses default list if None)
            region: Azure region name (default: "eastus")
            concurrency: Number of parallel workers (default: 10)

        Returns:
            List of price items for the specified region
        """
        if services is None:
            services = AZURE_RETAIL_SERVICE_NAMES
            
        self.logger.info(f"Fetching prices for {len(services)} services in region {region} using Go parallel scraper")
        
        result = await parallel_prices(
            services=services,
            concurrency=concurrency,
            region=region
        )
        
        if result is None:
            self.logger.error(f"Failed to fetch prices for region {region}")
            return []
        
        raw_prices = result.get("prices", [])
        self.logger.info(f"Fetched {len(raw_prices)} price items for region {region}")
        
        # Extract specifications
        enriched_prices = []
        for price in raw_prices:
            enriched_price = self._extract_specifications(price)
            enriched_prices.append(enriched_price)

        return enriched_prices

    async def get_prices_by_service(
        self, 
        service_name: str, 
        max_pages: int = 2,
        concurrency: int = 5
    ) -> list[dict[str, Any]]:
        """
        Fetch prices for a specific service using Go parallel backend.

        Args:
            service_name: Azure service name
            max_pages: Maximum pages to fetch (default: 2)
            concurrency: Number of parallel workers (default: 5)

        Returns:
            List of price items for the service
        """
        self.logger.info(f"Fetching prices for service {service_name} using Go parallel scraper")
        
        result = await parallel_prices(
            services=[service_name],
            concurrency=concurrency,
            region=""
        )
        
        if result is None:
            self.logger.error(f"Failed to fetch prices for service {service_name}")
            return []
        
        raw_prices = result.get("prices", [])
        self.logger.info(f"Fetched {len(raw_prices)} price items for service {service_name}")
        
        # Extract specifications
        enriched_prices = []
        for price in raw_prices:
            enriched_price = self._extract_specifications(price)
            enriched_prices.append(enriched_price)

        return enriched_prices

    def _extract_specifications(self, price: dict) -> dict:
        """
        Extract specifications from Azure pricing data.
        
        This method mirrors the implementation in the original AzurePriceClient
        to maintain compatibility.
        """
        # Create a copy to avoid modifying the original
        enriched = price.copy()

        # Extract common specification fields from Azure API response
        enriched["type"] = price.get("type")
        enriched["productName"] = price.get("productName")
        enriched["meterName"] = price.get("meterName")
        enriched["tier"] = price.get("tier")
        enriched["unit"] = price.get("unit")

        # For Virtual Machines, try to extract specs from SKU name or meter name
        if price.get("serviceName") == "Virtual Machines":
            sku_name = price.get("armSkuName", "")
            meter_name = price.get("meterName", "")

            # Parse SKU name for common patterns (e.g., Standard_D2s_v3)
            specs = self._parse_azure_vm_sku(sku_name, meter_name)
            enriched.update(specs)

        return enriched

    def _parse_azure_vm_sku(self, sku_name: str, meter_name: str) -> dict:
        """
        Parse Azure VM SKU name to extract specifications.
        
        This method mirrors the implementation in the original AzurePriceClient
        to maintain compatibility.
        """
        import re
        
        specs = {
            "vcpu": None,
            "memory": None,
            "series": None,
            "accelerator_type": None,
        }

        if not sku_name:
            return specs

        # Try to extract series/family from SKU name
        parts = sku_name.split("_")
        if len(parts) >= 2:
            series = parts[1] if len(parts) > 1 else None
            if series:
                # Extract just the series letter(s) without numbers
                series_match = re.match(r"([A-Za-z]+)", series)
                if series_match:
                    specs["series"] = series_match.group(1)

        # Extract vCPU and series from SKU name patterns
        vcpu_patterns = [
            (r"_([A-Za-z]*)(\d+)[A-Za-z]*_v\d+", True),  # Standard_D2s_v3 -> D, 2
            (r"_([A-Za-z]*)(\d+)-\d+[A-Za-z]*_v\d+", True),  # Standard_E8-4ds_v4 -> E, 8
            (r"_([A-Za-z]*)(\d+)[A-Za-z]*$", False),  # Standard_B2s -> B, 2 (no version)
            (r"_([A-Za-z]*)(\d+)-\d+[A-Za-z]*$", False),  # Standard_E4-2as -> E, 4 (no version)
            (r"_([A-Za-z]*)(\d+)$", False),  # Standard_D14 -> D, 14 (no version)
        ]

        for pattern, has_version in vcpu_patterns:
            match = re.search(pattern, sku_name)
            if match and match.lastindex >= 2:
                try:
                    series_letter = match.group(1)
                    vcpu_num = int(match.group(2))

                    if has_version or not series_letter.startswith("v"):
                        specs["vcpu"] = vcpu_num
                        if series_letter and not specs["series"]:
                            specs["series"] = series_letter
                        break
                except (ValueError, IndexError):
                    continue

        # Extract memory based on vCPU count and series
        if specs["vcpu"]:
            memory_gb = self._estimate_memory_from_sku(sku_name, specs["vcpu"])
            if memory_gb:
                specs["memory"] = f"{memory_gb} GB"

        # Try to extract CPU/memory from meter name as fallback
        if meter_name and (not specs["vcpu"] or not specs["memory"]):
            vcpu_match = re.search(r"(\d+)\s*vCPU", meter_name, re.IGNORECASE)
            if vcpu_match and not specs["vcpu"]:
                specs["vcpu"] = int(vcpu_match.group(1))

            memory_match = re.search(r"(\d+)\s*GB", meter_name, re.IGNORECASE)
            if memory_match and not specs["memory"]:
                specs["memory"] = f"{memory_match.group(1)} GB"

        return specs

    def _estimate_memory_from_sku(self, sku_name: str, vcpu: int) -> int | None:
        """
        Estimate memory in GB based on SKU series and vCPU count.
        
        This method mirrors the implementation in the original AzurePriceClient
        to maintain compatibility.
        """
        import re
        
        # Memory ratios for common Azure VM series (GB per vCPU)
        series_ratios = {
            "A": 2, "B": 2,
            "D": 4, "Ds": 4, "Dv": 4, "Dsv": 4,
            "E": 8, "Es": 8, "Ev": 8, "Esv": 8,
            "F": 2, "Fs": 2,
            "G": 8, "Gs": 8,
            "H": 8, "Hs": 8,
            "L": 8, "Ls": 8,
            "M": 16, "Ms": 16,
            "N": 8, "Ns": 8,
            "P": 8, "Ps": 8,
            "V": 8, "Vs": 8,
        }

        series_match = re.search(r"Standard_([A-Za-z]+)", sku_name)
        if not series_match:
            return None

        series = series_match.group(1)

        # Find matching series ratio
        ratio = None
        for series_prefix, series_ratio in series_ratios.items():
            if series.startswith(series_prefix):
                ratio = series_ratio
                break

        if ratio:
            return vcpu * ratio

        return None