import yaml
import os

class CostCalculator:
    def __init__(self, price_book_path='engine/price_book.yaml'):
        # Ensure we find the YAML file relative to the project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(project_root, price_book_path)
        
        try:
            with open(full_path, 'r') as f:
                self.prices = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"[!] ERROR: Price book not found at {full_path}")
            self.prices = {}

    def calculate_monthly_cost(self, provider, resource_type, sku, quantity=1):
        """
        Calculates monthly burn. 
        Converts hourly rates to 730-hour months.
        """
        try:
            rate = self.prices['providers'][provider][resource_type][sku]
            
            # If SKU represents a monthly rate (disks/ebs), return as is
            if 'month' in sku or resource_type in ['ebs', 'disk']:
                return float(rate) * quantity
            
            # Standard month = 730 hours
            return float(rate) * 730 * quantity
        except (KeyError, TypeError):
            # If SKU is missing, we return 0.0 to keep the reaper running
            return 0.0
