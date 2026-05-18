import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class CostCalculator:
    def __init__(self, price_book_path=None):
        if price_book_path is None:
            # Path relative to the current file
            price_book_path = Path(__file__).resolve().parent / "price_book.yaml"
        self.price_book_path = Path(price_book_path)
        try:
            with self.price_book_path.open() as f:
                self.prices = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load price book: {e}")
            self.prices = {"providers": {}}

        self.currency = "USD"

    def calculate_monthly_cost(self, provider, resource_type, sku, quantity=1):
        """Calculates cost based on SKU (e.g., 't3.micro' or 'Standard_B1s')."""
        try:
            rate = self.prices["providers"][provider][resource_type][sku]

            if resource_type in ["ebs", "disk", "storage"] or "per_gb_month" in sku:
                return rate * quantity

            return rate * 730 * quantity
        except KeyError:
            logger.warning(f"SKU {sku} not found in Price Book for {provider}.")
            return 0.0

    def calculate_hourly_cost(self, provider, resource_type, sku, quantity=1):
        """Calculates hourly burn rate based on SKU."""
        try:
            rate = self.prices["providers"][provider][resource_type][sku]

            if resource_type in ["ebs", "disk", "storage"] or "per_gb_month" in sku:
                return (rate * quantity) / 730

            return rate * quantity
        except KeyError:
            logger.warning(f"SKU {sku} not found in Price Book for {provider}.")
            return 0.0

    def calculate_total_hourly_burn(self, burn_items):
        """Normalizes a list of burn items into a total hourly rate."""
        total = 0.0
        for item in burn_items:
            provider = item.get("provider")
            resource_type = item.get("resource_type")
            sku = item.get("sku")
            quantity = item.get("quantity", 1)
            frequency = item.get("frequency", "hourly")

            if frequency == "monthly":
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
        items = price_data.get("prices", []) if isinstance(price_data, dict) else price_data

        if not isinstance(items, list):
            logger.warning("Invalid price data format received.")
            return

        for item in items:
            try:
                # Normalizing Azure Retail Prices API schema
                service = item.get("serviceName", "").lower()
                sku = item.get("armSkuName", item.get("meterName", "")).lower()
                price = item.get("retailPrice", 0.0)

                # Internal mapping: Azure API 'Virtual Machines' -> 'compute'
                category = None
                if "virtual machines" in service:
                    category = "compute"
                elif "storage" in service:
                    category = "storage"

                if category and sku:
                    if "azure" not in self.prices["providers"]:
                        self.prices["providers"]["azure"] = {}
                    if category not in self.prices["providers"]["azure"]:
                        self.prices["providers"]["azure"][category] = {}

                    # Store both SKU and normalized SKU
                    self.prices["providers"]["azure"][category][sku] = price

                    # Also map to 'disk' if it's storage for compatibility
                    if category == "storage":
                        if "disk" not in self.prices["providers"]["azure"]:
                            self.prices["providers"]["azure"]["disk"] = {}
                        self.prices["providers"]["azure"]["disk"][sku] = price

            except Exception as e:
                logger.debug(f"Error processing price item: {e}")
                continue

        logger.info(f"Price Book synchronized with {len(items)} live entries.")

    def reload_prices(self):
        """
        Reloads the price book from YAML file.
        Returns True if successful, False otherwise.
        """
        try:
            with self.price_book_path.open() as f:
                self.prices = yaml.safe_load(f)
            return True
        except FileNotFoundError:
            logger.error(f"Price book file not found at {self.price_book_path}")
            return False
        except Exception as e:
            logger.error(f"Error reloading price book: {e}")
            return False

    def set_currency(self, currency_code):
        """
        Sets the currency for cost calculations.
        Currently stores the currency code (future: could implement conversion).
        """
        valid_currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY"]
        if currency_code.upper() in valid_currencies:
            self.currency = currency_code.upper()
            return True
        logger.error(f"Unsupported currency code {currency_code}")
        return False

    def format_price(self, amount):
        """Formats a float as a currency string."""
        symbols = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
        symbol = symbols.get(self.currency, "$")
        return f"{symbol}{amount:,.2f}"


import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

class RightsizingAgent:
    """
    Reinforcement Learning (Q-learning) Workload Rightsizing Agent.
    State space: CPU, memory, IOPS, and network bandwidth.
    Action space: Stay, Downscale, Upscale, Migrate Family (e.g., D-series to E-series).
    """
    def __init__(self, learning_rate=0.1, discount_factor=0.9, exploration_rate=1.0):
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.actions = ["stay", "downscale", "upscale", "migrate_family"]
        self.q_table = {}

    def get_state(self, cpu, mem, iops, net):
        def discretize(val):
            if val < 30: return 0
            if val < 70: return 1
            return 2
        return (discretize(cpu), discretize(mem), discretize(iops), discretize(net))

    def choose_action(self, state):
        if state not in self.q_table:
            self.q_table[state] = np.zeros(len(self.actions))
        
        # Epsilon-greedy for training
        if np.random.uniform(0, 1) < self.epsilon:
            return np.random.choice(len(self.actions))
        return np.argmax(self.q_table[state])

    def learn(self, state, action, reward, next_state):
        if state not in self.q_table:
            self.q_table[state] = np.zeros(len(self.actions))
        if next_state not in self.q_table:
            self.q_table[next_state] = np.zeros(len(self.actions))
            
        predict = self.q_table[state][action]
        target = reward + self.gamma * np.max(self.q_table[next_state])
        self.q_table[state][action] = self.q_table[state][action] + self.lr * (target - predict)

    def evaluate_migration(self, cpu_util, mem_util, iops, net, current_sku):
        """
        Evaluates safe down-scaling or cross-family migrations.
        Builds risk profiles ensuring performance SLAs are maintained while minimizing cost.
        """
        # Inference mode (exploit)
        self.epsilon = 0.0
        state = self.get_state(cpu_util, mem_util, iops, net)
        action_idx = self.choose_action(state)
        action = self.actions[action_idx]
        
        risk_profile = "Low"
        if action == "migrate_family" and (mem_util > 80 or cpu_util > 80):
            risk_profile = "High"
        elif action == "downscale" and max(cpu_util, mem_util) > 60:
            risk_profile = "Medium"
            
        return {
            "recommended_action": action,
            "risk_profile": risk_profile,
            "sla_maintained": risk_profile != "High",
            "current_sku": current_sku,
        }

class SpotEvictionPredictor:
    """
    Spot Instance Interruption and Bidding Predictor using a Gradient-Boosted Tree.
    Predicts the probability of eviction for a Spot instance within the next 1 to 4 hours.
    """
    def __init__(self):
        self.is_trained = False
        # Lightweight Gradient Boosted model
        self.model = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3)

    def train(self, telemetry_data):
        """
        telemetry_data: list of dicts with keys ['price_volatility', 'demand_index', 'region_capacity', 'evicted']
        """
        df = pd.DataFrame(telemetry_data)
        if df.empty or 'evicted' not in df.columns:
            return

        X = df[['price_volatility', 'demand_index', 'region_capacity']]
        y = df['evicted']
        
        self.model.fit(X, y)
        self.is_trained = True

    def predict_eviction_probability(self, price_volatility, demand_index, region_capacity):
        if not self.is_trained:
            # Fallback heuristic if not trained
            prob = (price_volatility * 0.4) + (demand_index * 0.5) + ((100 - region_capacity) * 0.01)
            return min(max(prob, 0.0), 1.0)

        X_test = pd.DataFrame([{
            'price_volatility': price_volatility,
            'demand_index': demand_index,
            'region_capacity': region_capacity
        }])
        
        # Probability of class 1 (evicted)
        prob = self.model.predict_proba(X_test)[0][1]
        return float(prob)

    def monitor_and_trigger(self, instance_id, region, telemetry):
        """
        telemetry: dict with 'price_volatility' (0-1), 'demand_index' (0-1), 'region_capacity' (0-100)
        """
        prob = self.predict_eviction_probability(
            telemetry.get('price_volatility', 0.5),
            telemetry.get('demand_index', 0.5),
            telemetry.get('region_capacity', 50.0)
        )
        
        trigger_migration = prob >= 0.90
        
        action = "migrate_gracefully" if trigger_migration else "monitor"
        msg = f"90% chance of eviction detected! Triggering automated migration for {instance_id} to stable region." if trigger_migration else "Instance is stable."

        return {
            "instance_id": instance_id,
            "region": region,
            "eviction_probability": round(prob, 4),
            "action_required": action,
            "message": msg
        }

# Validation block
if __name__ == "__main__":
    calc = CostCalculator()
    aws_test = calc.calculate_monthly_cost("aws", "ec2", "t3.micro")
    print(f"Projected Monthly Cost for AWS t3.micro: ${aws_test:.2f}")

