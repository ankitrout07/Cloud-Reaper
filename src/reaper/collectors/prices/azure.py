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

        return all_prices

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
