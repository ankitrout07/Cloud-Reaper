import yaml
import os

class CostCalculator:
    def __init__(self, price_book_path='engine/price_book.yaml'):
        with open(price_book_path, 'r') as f:
            self.prices = yaml.safe_load(f)

    def calculate_monthly_cost(self, provider, resource_type, sku, quantity=1):
        """Calculates cost based on SKU (e.g., 't3.micro' or 'Standard_B1s')."""
        try:
            rate = self.prices['providers'][provider][resource_type][sku]
            
            if resource_type in ['ebs', 'disk', 'storage'] or 'per_gb_month' in sku:
                return rate * quantity

            return rate * 730 * quantity
        except KeyError:
            print(f"[!] Warning: SKU {sku} not found in Price Book for {provider}.")
            return 0.0

    def calculate_hourly_cost(self, provider, resource_type, sku, quantity=1):
        """Calculates hourly burn rate based on SKU."""
        try:
            rate = self.prices['providers'][provider][resource_type][sku]

            if resource_type in ['ebs', 'disk', 'storage'] or 'per_gb_month' in sku:
                return (rate * quantity) / 730

            return rate * quantity
        except KeyError:
            print(f"[!] Warning: SKU {sku} not found in Price Book for {provider}.")
            return 0.0

    def calculate_total_hourly_burn(self, burn_items):
        """Normalizes a list of burn items into a total hourly rate."""
        total = 0.0
        for item in burn_items:
            provider = item.get('provider')
            resource_type = item.get('resource_type')
            sku = item.get('sku')
            quantity = item.get('quantity', 1)
            frequency = item.get('frequency', 'hourly')

            if frequency == 'monthly':
                total += self.calculate_monthly_cost(provider, resource_type, sku, quantity) / 730
            else:
                total += self.calculate_hourly_cost(provider, resource_type, sku, quantity)

        return round(total, 6)

    def load_prices(self, price_data):
        """
        Dynamically updates the price book with live data from the Go collector.
        Supports both raw list of price items and wrapped ScanResult dictionary.
        """
        if not price_data:
            return

        # Extract items if wrapped in 'prices' key
        items = price_data.get('prices', []) if isinstance(price_data, dict) else price_data
        
        if not isinstance(items, list):
            print("[!] Warning: Invalid price data format received.")
            return

        for item in items:
            try:
                # Normalizing Azure Retail Prices API schema
                service = item.get('serviceName', '').lower()
                sku = item.get('armSkuName', item.get('meterName', '')).lower()
                price = item.get('retailPrice', 0.0)
                
                # Internal mapping: Azure API 'Virtual Machines' -> 'compute', 'Storage' -> 'storage'
                category = None
                if 'virtual machines' in service:
                    category = 'compute'
                elif 'storage' in service:
                    category = 'storage'
                
                if category and sku:
                    if 'azure' not in self.prices['providers']:
                        self.prices['providers']['azure'] = {}
                    if category not in self.prices['providers']['azure']:
                        self.prices['providers']['azure'][category] = {}
                    
                    # Store both SKU and normalized SKU
                    self.prices['providers']['azure'][category][sku] = price
                    
                    # Also map to 'disk' if it's storage for main.py compatibility
                    if category == 'storage':
                        if 'disk' not in self.prices['providers']['azure']:
                            self.prices['providers']['azure']['disk'] = {}
                        self.prices['providers']['azure']['disk'][sku] = price

            except Exception as e:
                continue

        print(f"    [+] Price Book synchronized with {len(items)} live entries.")

    # TODO: Implement real-time pricing using Azure Retail Prices API

# Validation block
if __name__ == "__main__":
    calc = CostCalculator()
    aws_test = calc.calculate_monthly_cost('aws', 'ec2', 't3.micro')
    print(f"Projected Monthly Cost for AWS t3.micro: ${aws_test:.2f}")