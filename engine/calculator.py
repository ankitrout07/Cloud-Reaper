import yaml
import os
from collectors.azure_prices import AzurePriceClient

class CostCalculator:
    def __init__(self, price_book_path='engine/price_book.yaml', currency='USD'):
        # Ensure we find the YAML file relative to the project root
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.path = os.path.join(self.project_root, price_book_path)
        self.currency = currency
        self.exchange_rate = 83.0  # Static for now
        self.load_config()

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

    def set_currency(self, code):
        if code in ["USD", "INR"]:
            self.currency = code
            self.azure_price_client = AzurePriceClient(currency=code)
            # Clear cache to force re-fetch in new currency if needed
            self.price_cache = {}
            return True
        return False

    def format_price(self, usd_amount):
        if self.currency == "INR":
            return f"₹{round(usd_amount * self.exchange_rate, 2)}"
        return f"${round(usd_amount, 2)}"




    def load_prices(self, price_items):
        """Loads a list of price items (from Azure Retail API format) into the cache."""
        for item in price_items:
            # Check both armResourceName and armSkuName for maximum compatibility
            arm_name = item.get('armResourceName') or item.get('armSkuName')
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

    def calculate_waste_coefficient(self, utilization_pct, cost_per_month):
        """
        Calculates EfficiencyScore = AvgUtilization% / CostPerUnit
        Returns a lower number for higher waste.
        If cost is 0, returns a default high score.
        """
        if cost_per_month <= 0:
            return 100.0
        # If a $500 VM has 5% utilization, score = 5 / 500 = 0.01 (High Waste)
        # If a $50 VM has 90% utilization, score = 90 / 50 = 1.8 (High Efficiency)
        return round(utilization_pct / cost_per_month, 4)

    def calculate_carbon_emission(self, region, vcpu_count, hours=730):
        """
        Calculates estimated carbon footprint based on Azure Region.
        Returns emissions in kgCO2e.
        """
        # Simplified emission factors (gCO2e per kWh)
        # Assuming 1 vCPU ~ 3.5 watts/hour on average for calculation simplicity
        emission_factors = {
            "centralindia": 700, # High carbon (coal heavy)
            "eastus": 400,
            "westeurope": 200,
            "northeurope": 150,
            "swedencentral": 10, # Very low carbon (renewable)
            "norwayeast": 15,
            "default": 350
        }
        
        region_key = str(region).lower().replace(" ", "")
        factor = emission_factors.get(region_key, emission_factors["default"])
        
        # Power calculation: vCPU * 3.5 watts * hours = Watt-hours
        # kWh = Watt-hours / 1000
        kwh = (vcpu_count * 3.5 * hours) / 1000.0
        
        # Emissions in grams, convert to kg
        kg_co2e = (kwh * factor) / 1000.0
        return round(kg_co2e, 2)
