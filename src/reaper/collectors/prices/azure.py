import logging

import requests

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


class AzurePriceClient:
    BASE_URL = "https://prices.azure.com/api/retail/prices"

    def __init__(self, currency="USD"):
        self.currency = currency
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        self.logger = logging.getLogger(__name__)

    def get_prices(self, filter_query=None, max_pages=None):
        """
        Fetches prices from the Azure Retail Prices API with pagination support.
        """
        params = {"currencyCode": self.currency}
        if filter_query:
            params["$filter"] = filter_query

        prices = []
        url = self.BASE_URL
        page_count = 0

        while url:
            try:
                response = self.session.get(
                    url,
                    params=params if url == self.BASE_URL else None,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("Items", [])
                prices.extend(items)
                page_count += 1

                if max_pages is not None and page_count >= max_pages:
                    break

                url = data.get("NextPageLink")
                # Once we have NextPageLink, params are already included in the URL
                params = None

            except Exception as e:
                self.logger.error(f"Error fetching prices from Azure: {e}")
                break

        return prices

    def get_catalog_prices(self):
        """Fetch the Azure Retail Prices API catalog for all supported service categories."""
        all_prices = []
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_svc = {
                executor.submit(self.get_prices_by_service, service, 2): service
                for service in AZURE_RETAIL_SERVICE_NAMES
            }
            for future in concurrent.futures.as_completed(future_to_svc):
                try:
                    all_prices.extend(future.result())
                except Exception as exc:
                    self.logger.error(f"Error fetching Azure catalog prices: {exc}")

        # Extract specifications from the raw pricing data
        enriched_prices = []
        for price in all_prices:
            enriched_price = self._extract_specifications(price)
            enriched_prices.append(enriched_price)

        return enriched_prices

    def _extract_specifications(self, price: dict) -> dict:
        """Extract specifications from Azure pricing data."""
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
        """Parse Azure VM SKU name to extract specifications."""
        specs = {
            "vcpu": None,
            "memory": None,
            "series": None,
            "accelerator_type": None,
        }

        if not sku_name:
            return specs

        import re

        # Try to extract series/family from SKU name
        # Examples: Standard_D2s_v3, Standard_E4-2ds_v4, Basic_A0
        parts = sku_name.split("_")
        if len(parts) >= 2:
            series = parts[1] if len(parts) > 1 else None
            if series:
                # Extract just the series letter(s) without numbers
                # D2s -> D, NC6s -> NC, E8-4ds -> E
                series_match = re.match(r"([A-Za-z]+)", series)
                if series_match:
                    specs["series"] = series_match.group(1)

        # Extract vCPU and series from SKU name patterns
        # Standard_D2s_v3 -> series=D, vcpu=2
        # Standard_E8-4ds_v4 -> series=E, vcpu=8
        # Standard_B2s -> series=B, vcpu=2
        # Standard_NC6s_v3 -> series=NC, vcpu=6
        # Standard_NP96s -> series=NP, vcpu=96
        # Standard_D14 -> series=D, vcpu=14
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
                    
                    # Only use this pattern if it doesn't incorrectly match version numbers
                    # Patterns with "_v" are safe (has_version=True)
                    # Patterns without "_v" need to check they're not matching version suffixes
                    if has_version or not series_letter.startswith("v"):
                        specs["vcpu"] = vcpu_num
                        # Don't override series if already set
                        if series_letter and not specs["series"]:
                            specs["series"] = series_letter
                        break
                except (ValueError, IndexError):
                    continue

        # Extract memory based on vCPU count and series
        # Azure VM series have typical memory-to-vCPU ratios
        if specs["vcpu"]:
            memory_gb = self._estimate_memory_from_sku(sku_name, specs["vcpu"])
            if memory_gb:
                specs["memory"] = f"{memory_gb} GB"

        # Try to extract CPU/memory from meter name as fallback
        if meter_name and (not specs["vcpu"] or not specs["memory"]):
            # Look for patterns like "2 vCPU", "4 vCPU", "8 vCPU"
            vcpu_match = re.search(r"(\d+)\s*vCPU", meter_name, re.IGNORECASE)
            if vcpu_match and not specs["vcpu"]:
                specs["vcpu"] = int(vcpu_match.group(1))

            # Look for memory patterns like "8 GB", "16 GB", "32 GB"
            memory_match = re.search(r"(\d+)\s*GB", meter_name, re.IGNORECASE)
            if memory_match and not specs["memory"]:
                specs["memory"] = f"{memory_match.group(1)} GB"

        return specs

    def _estimate_memory_from_sku(self, sku_name: str, vcpu: int) -> int | None:
        """Estimate memory in GB based on SKU series and vCPU count."""
        # Memory ratios for common Azure VM series (GB per vCPU)
        series_ratios = {
            # A series
            "A": 2,
            "B": 2,
            # D series (general purpose)
            "D": 4,
            "Ds": 4,
            "Dv": 4,
            "Dsv": 4,
            # E series (memory optimized)
            "E": 8,
            "Es": 8,
            "Ev": 8,
            "Esv": 8,
            # F series (compute optimized)
            "F": 2,
            "Fs": 2,
            # G series (memory optimized)
            "G": 8,
            "Gs": 8,
            # H series (high performance compute)
            "H": 8,
            "Hs": 8,
            # L series (storage optimized)
            "L": 8,
            "Ls": 8,
            # M series (memory optimized)
            "M": 16,
            "Ms": 16,
            # N series (GPU)
            "N": 8,
            "Ns": 8,
            # P series (GPU)
            "P": 8,
            "Ps": 8,
            # V series (memory optimized)
            "V": 8,
            "Vs": 8,
        }

        # Extract series from SKU name
        import re
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

    def get_prices_by_service(self, service_name, max_pages=None):
        filter_query = f"serviceName eq '{service_name}' and priceType eq 'Consumption'"
        return self.get_prices(filter_query, max_pages=max_pages)

    def get_prices_by_resource_name(self, sku_name):
        # Using armSkuName is often more reliable than armResourceName for many services
        filter_query = f"armSkuName eq '{sku_name}' and priceType eq 'Consumption'"
        return self.get_prices(filter_query)

    def get_category_prices(self, category):
        """
        Maps categories to service names and fetches prices.
        Categories: Compute, Networking, Storage
        """
        category_map = {
            "Compute": ["Virtual Machines", "Cloud Services"],
            "Networking": ["Networking", "Bandwidth"],
            "Storage": ["Storage"],
        }

        services = category_map.get(category, [])
        all_prices = []
        for service in services:
            all_prices.extend(self.get_prices_by_service(service))
        return all_prices
