import yaml
import os
from collectors.azure_prices import AzurePriceClient

class CostCalculator:
    def __init__(self, price_book_path='engine/price_book.yaml', currency='USD'):
        # Ensure we find the YAML file relative to the project root
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.path = os.path.join(self.project_root, price_book_path)
        self.load_config()

        self.currency = currency
        self.azure_price_client = AzurePriceClient(currency=currency)
        self.price_cache = {}

        # Hardcoded prices for the new Tier Logic as requested
        self.prices = {
            "unassociated_ip": 0.005,
            "idle_lb": 0.025,
            "premium_ssd_p6": 0.008, # Hourly approx ($5.89/730)
            "standard_b2s": 0.0416
        }

    def load_config(self):
        """Loads or reloads the pricing YAML file"""
        if os.path.exists(self.path):
            with open(self.path, 'r') as f:
                self.prices_yaml = yaml.safe_load(f)
            return True
        else:
            print(f"[!] ERROR: Price book not found at {self.path}")
            self.prices_yaml = {}
            return False

    def reload_prices(self):
        return self.load_config()

    def set_currency(self, currency):
        self.currency = currency
        self.azure_price_client = AzurePriceClient(currency=currency)
        # Clear cache to force re-fetch in new currency if needed
        self.price_cache = {}



    def load_prices(self, price_items):
        """Loads a list of price items (from Azure Retail API format) into the cache."""
        for item in price_items:
            arm_name = item.get('armResourceName')
            if arm_name and item.get('type') == 'Consumption':
                price = item.get('retailPrice', 0.0)
                # Store the first one we find, or we could be more specific
                if arm_name not in self.price_cache or self.price_cache[arm_name] == 0.0:
                    self.price_cache[arm_name] = price

    def _get_azure_live_price(self, arm_resource_name):
        """Fetches live price from Azure Retail Prices API if not in cache."""
        if arm_resource_name in self.price_cache and self.price_cache[arm_resource_name] > 0:
            return self.price_cache[arm_resource_name]
        
        # Fallback to API if not in bulk loaded cache
        try:
            results = self.azure_price_client.get_prices_by_resource_name(arm_resource_name)
            if results:
                retail_prices = [p for p in results if p.get('type') == 'Consumption']
                if retail_prices:
                    price = retail_prices[0].get('retailPrice', 0.0)
                    self.price_cache[arm_resource_name] = price
                    return price
        except Exception as e:
            print(f"[!] Error fetching live price for {arm_resource_name}: {e}")
            
        return self.price_cache.get(arm_resource_name, 0.0)

    def calculate_monthly_cost(self, provider, resource_type, sku, quantity=1):
        """
        Calculates monthly burn. 
        Converts hourly rates to 730-hour months.
        """
        # For Azure, try live API first if it's a known SKU format
        if provider == 'azure':
            live_price = self._get_azure_live_price(sku)
            if live_price > 0:
                # Azure Retail API usually returns hourly prices
                return float(live_price) * 730 * quantity

        try:
            rate = self.prices_yaml['providers'][provider][resource_type][sku]
            
            # If SKU represents a monthly rate (disks/ebs), return as is
            if 'month' in sku or resource_type in ['ebs', 'disk']:
                return float(rate) * quantity
            
            # Standard month = 730 hours
            return float(rate) * 730 * quantity
        except (KeyError, TypeError):
            # Fallback to hardcoded prices if not in YAML
            return self.prices.get(sku, 0.0) * 730 * quantity

    def categorize_resource(self, resource_type, state, usage=None):
        """
        Returns (priority, risk_level, hourly_waste)
        """
        if state == "orphaned":
            return "P1", "Low Risk", self.prices.get(resource_type, 0)
        
        if state == "idle":
            # Usage is low but it is running; higher risk to delete
            return "P2", "Medium Risk", self.prices.get(resource_type, 0)
            
        return "P3", "Check Manually", 0.0

