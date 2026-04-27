import requests
import json
import logging

class AzurePriceClient:
    BASE_URL = "https://prices.azure.com/api/retail/prices"

    def __init__(self, currency='USD'):
        self.currency = currency
        self.session = requests.Session()
        self.logger = logging.getLogger(__name__)

    def get_prices(self, filter_query=None):
        """
        Fetches prices from the Azure Retail Prices API with pagination support.
        """
        params = {'currencyCode': self.currency}
        if filter_query:
            params['$filter'] = filter_query

        prices = []
        url = self.BASE_URL
        
        while url:
            try:
                response = self.session.get(url, params=params if url == self.BASE_URL else None)
                response.raise_for_status()
                data = response.json()
                
                items = data.get('Items', [])
                prices.extend(items)
                
                url = data.get('NextPageLink')
                # Once we have NextPageLink, params are already included in the URL
                params = None 
                
            except Exception as e:
                self.logger.error(f"Error fetching prices from Azure: {e}")
                break
        
        return prices

    def get_prices_by_service(self, service_name):
        filter_query = f"serviceName eq '{service_name}' and priceType eq 'Consumption'"
        return self.get_prices(filter_query)

    def get_prices_by_resource_name(self, arm_resource_name):
        filter_query = f"armResourceName eq '{arm_resource_name}' and priceType eq 'Consumption'"
        return self.get_prices(filter_query)

    def get_category_prices(self, category):
        """
        Maps categories to service names and fetches prices.
        Categories: Compute, Networking, Storage
        """
        category_map = {
            'Compute': ['Virtual Machines', 'Cloud Services'],
            'Networking': ['Networking', 'Bandwidth'],
            'Storage': ['Storage']
        }
        
        services = category_map.get(category, [])
        all_prices = []
        for service in services:
            all_prices.extend(self.get_prices_by_service(service))
        return all_prices
