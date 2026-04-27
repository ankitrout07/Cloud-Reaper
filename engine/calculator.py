import yaml
import os

class CostCalculator:
    def __init__(self, price_book_path='engine/price_book.yaml'):
        # Ensure we find the YAML file relative to the project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(project_root, price_book_path)
        
        try:
            with open(full_path, 'r') as f:
                self.prices_yaml = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"[!] ERROR: Price book not found at {full_path}")
            self.prices_yaml = {}

        # Hardcoded prices for the new Tier Logic as requested
        self.prices = {
            "unassociated_ip": 0.005,
            "idle_lb": 0.025,
            "premium_ssd_p6": 0.008, # Hourly approx ($5.89/730)
            "standard_b2s": 0.0416
        }

    def calculate_monthly_cost(self, provider, resource_type, sku, quantity=1):
        """
        Calculates monthly burn. 
        Converts hourly rates to 730-hour months.
        """
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

