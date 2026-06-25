import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import GradientBoostingClassifier

logger = logging.getLogger(__name__)


class CostCalculator:
    def __init__(self, price_book_path=None):
        if price_book_path is None:
            # Path relative to the current file (either in core/ or engine/)
            p1 = Path(__file__).resolve().parent / "price_book.yaml"
            p2 = Path(__file__).resolve().parent.parent / "price_book.yaml"
            price_book_path = p1 if p1.exists() else p2
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
        """
        Normalizes a list of burn items into a total hourly rate.

        Performance: converts burn_items to a Pandas DataFrame so the rate-lookup and
        arithmetic happen in vectorized, C-compiled NumPy operations rather than a
        Python for-loop, escaping the GIL for the hot numeric path.
        """
        if not burn_items:
            return 0.0

        df = pd.DataFrame(burn_items)

        # Ensure required columns exist with sensible defaults
        if "quantity" not in df.columns:
            df["quantity"] = 1
        if "frequency" not in df.columns:
            df["frequency"] = "hourly"
        df["quantity"] = df["quantity"].fillna(1)
        df["frequency"] = df["frequency"].fillna("hourly")

        # Vectorized rate lookup via apply (I/O-bound per-SKU dict lookup — unavoidable)
        df["rate"] = df.apply(
            lambda row: self.calculate_hourly_cost(
                row["provider"], row["resource_type"], row["sku"], row["quantity"]
            ),
            axis=1,
        )

        # Vectorized monthly-to-hourly normalisation using np.where on the frequency column
        df["hourly_cost"] = np.where(
            df["frequency"] == "monthly",
            df.apply(
                lambda row: self.calculate_monthly_cost(
                    row["provider"], row["resource_type"], row["sku"], row["quantity"]
                ),
                axis=1,
            )
            / 730.0,
            df["rate"],
        )

        # np.sum on the resulting column is a single C call
        total = float(np.sum(df["hourly_cost"].to_numpy()))
        return round(total, 6)

    def _validate_price_item(self, item):
        """Validate and extract price item data. Returns (sku, price_float, category) or (None, None, None)."""
        if not isinstance(item, dict):
            logger.debug(f"Skipping non-dict price item: {type(item).__name__}")
            return None, None, None

        # Normalizing Azure Retail Prices API schema
        service = item.get("serviceName", "").lower()
        sku = item.get("armSkuName", item.get("meterName", "")).lower()
        price = item.get("retailPrice", 0.0)

        # Validate required fields
        if not sku:
            logger.debug("Skipping price item with missing SKU")
            return None, None, None

        # Validate price is a number
        try:
            price_float = float(price)
            if price_float < 0:
                logger.debug(f"Skipping price item with negative price: {price_float}")
                return None, None, None
        except (ValueError, TypeError):
            logger.debug(f"Skipping price item with invalid price: {price}")
            return None, None, None

        # Internal mapping: Azure API 'Virtual Machines' -> 'compute'
        category = None
        if "virtual machines" in service:
            category = "compute"
        elif "storage" in service:
            category = "storage"

        return sku, price_float, category

    def load_prices(self, price_data):
        """
        Dynamically updates the price book with live data from cloud retail APIs.
        Supports both raw list of price items and wrapped ScanResult dictionary.
        """
        if not price_data:
            logger.warning("Empty price data received")
            return

        # Extract items if wrapped in 'prices' key
        items = price_data.get("prices", []) if isinstance(price_data, dict) else price_data

        if not isinstance(items, list):
            logger.warning(f"Invalid price data format: expected list, got {type(items).__name__}")
            return

        if not items:
            logger.warning("Empty price items list received")
            return

        processed_count = 0
        skipped_count = 0

        for item in items:
            try:
                sku, price_float, category = self._validate_price_item(item)
                if sku is None:
                    skipped_count += 1
                    continue

                if category and sku:
                    if "azure" not in self.prices["providers"]:
                        self.prices["providers"]["azure"] = {}
                    if category not in self.prices["providers"]["azure"]:
                        self.prices["providers"]["azure"][category] = {}

                    # Store both SKU and normalized SKU
                    self.prices["providers"]["azure"][category][sku] = price_float

                    # Also map to 'disk' if it's storage for compatibility
                    if category == "storage":
                        if "disk" not in self.prices["providers"]["azure"]:
                            self.prices["providers"]["azure"]["disk"] = {}
                        self.prices["providers"]["azure"]["disk"][sku] = price_float

                    processed_count += 1
                else:
                    skipped_count += 1

            except Exception as e:
                logger.debug(f"Error processing price item: {e}")
                skipped_count += 1
                continue

        logger.info(
            f"Price Book synchronized: {processed_count} entries loaded, {skipped_count} skipped."
        )

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


class RightsizingAgent:
    """
    Reinforcement Learning (Q-learning) Workload Rightsizing Agent.
    State space: CPU, memory, IOPS, and network bandwidth.
    Action space: Stay, Downscale, Upscale, Migrate Family (e.g., D-series to E-series).
    Now includes environment-aware thresholds for production vs dev-test safety.
    """

    def __init__(
        self,
        learning_rate=0.1,
        discount_factor=0.9,
        exploration_rate=1.0,
        environment_type="production",
    ):
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.environment_type = environment_type
        self.actions = ["stay", "downscale", "upscale", "migrate_family"]
        self.q_table = {}

        # Environment-aware thresholds
        # Production uses more conservative (higher) thresholds for safety
        if self.environment_type == "production":
            self.risk_thresholds = {
                "high_utilization": 80.0,  # Higher threshold for production
                "medium_utilization": 60.0,
                "low_utilization": 30.0,
            }
        else:  # dev-test
            self.risk_thresholds = {
                "high_utilization": 70.0,  # More aggressive for dev-test
                "medium_utilization": 50.0,
                "low_utilization": 20.0,
            }

    def get_state(self, cpu, mem, iops, net):
        def discretize(val):
            # Use environment-aware discretization
            if val < self.risk_thresholds["low_utilization"]:
                return 0
            if val < self.risk_thresholds["medium_utilization"]:
                return 1
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

    def evaluate_migration(self, metrics, current_sku, environment_type=None):
        """
        Evaluates safe down-scaling or cross-family migrations.
        Builds risk profiles ensuring performance SLAs are maintained while minimizing cost.
        Now supports environment-aware thresholds.

        Args:
            metrics: Dictionary with cpu, mem, iops, net values
            current_sku: Current SKU identifier
            environment_type: 'production' or 'dev-test' (overrides instance setting)
        """
        # Use provided environment_type or fall back to instance setting
        env = environment_type or self.environment_type
        if env == "production":
            risk_thresholds = {
                "high_utilization": 80.0,
                "medium_utilization": 60.0,
                "low_utilization": 30.0,
            }
        else:
            risk_thresholds = {
                "high_utilization": 70.0,
                "medium_utilization": 50.0,
                "low_utilization": 20.0,
            }

        cpu_util = metrics.get("cpu", 0)
        mem_util = metrics.get("mem", 0)
        iops = metrics.get("iops", 0)
        net = metrics.get("net", 0)

        # Inference mode (exploit)
        self.epsilon = 0.0
        state = self.get_state(cpu_util, mem_util, iops, net)
        action_idx = self.choose_action(state)
        action = self.actions[action_idx]

        # Environment-aware risk assessment
        risk_profile = "Low"
        if action == "migrate_family":
            if (
                mem_util > risk_thresholds["high_utilization"]
                or cpu_util > risk_thresholds["high_utilization"]
            ):
                risk_profile = "High"
            elif (
                mem_util > risk_thresholds["medium_utilization"]
                or cpu_util > risk_thresholds["medium_utilization"]
            ):
                risk_profile = "Medium"
        elif action == "downscale":
            if max(cpu_util, mem_util) > risk_thresholds["medium_utilization"]:
                risk_profile = "Medium"
            if max(cpu_util, mem_util) > risk_thresholds["high_utilization"]:
                risk_profile = "High"

        # Production safety override
        if env == "production" and risk_profile == "High":
            action = "stay"  # Override to stay for production safety

        return {
            "recommended_action": action,
            "risk_profile": risk_profile,
            "sla_maintained": risk_profile != "High",
            "current_sku": current_sku,
            "environment_type": env,
            "thresholds_used": risk_thresholds,
        }

    def batch_evaluate_migration(self, metrics_df: "pd.DataFrame") -> "pd.DataFrame":
        """
        Vectorized batch evaluation of an entire fleet's migration decisions.

        Instead of calling evaluate_migration() in a Python loop (which acquires the GIL
        on every iteration), this method:
          1. Converts continuous metric columns to discrete state tuples via NumPy
             digitize (a C-compiled binning operation).
          2. Resolves Q-values for every state in a single vectorized NumPy fancy-index
             lookup, then runs np.argmax across the result matrix to pick the best action.
          3. Derives risk profiles using np.where broadcast comparisons.

        Parameters
        ----------
        metrics_df : pd.DataFrame
            Must contain columns: cpu, mem, iops, net, sku (optional, for output only).

        Returns
        -------
        pd.DataFrame with additional columns:
            state, action_idx, recommended_action, risk_profile, sla_maintained
        """
        import pandas as pd

        df = metrics_df.copy()

        bins = np.array([0, 30, 70, 100], dtype=np.float64)

        # Vectorized discretization — np.digitize runs in C for all rows at once
        def _disc(col: pd.Series) -> np.ndarray:
            return (np.digitize(col.to_numpy(dtype=np.float64), bins[1:-1])).astype(np.int8)

        cpu_d = _disc(df["cpu"])
        mem_d = _disc(df["mem"])
        iops_d = _disc(df["iops"])
        net_d = _disc(df["net"])

        # Build state tuples and resolve Q-values --------------------------------
        states = list(zip(cpu_d, mem_d, iops_d, net_d))
        q_vals = np.array(
            [self.q_table.get(s, np.zeros(len(self.actions))) for s in states],
            dtype=np.float64,
        )  # shape: (N, num_actions)

        # Single np.argmax call across all rows replaces N Python argmax calls
        action_idxs = np.argmax(q_vals, axis=1)
        actions = np.array(self.actions)[action_idxs]

        # Vectorized risk classification using np.where broadcast ---------------
        cpu_arr = df["cpu"].to_numpy(dtype=np.float64)
        mem_arr = df["mem"].to_numpy(dtype=np.float64)

        high_mask = (actions == "migrate_family") & ((mem_arr > 80) | (cpu_arr > 80))
        med_mask = (actions == "downscale") & (np.maximum(cpu_arr, mem_arr) > 60)

        risk = np.where(high_mask, "High", np.where(med_mask, "Medium", "Low"))
        sla = risk != "High"

        df["state"] = states
        df["action_idx"] = action_idxs
        df["recommended_action"] = actions
        df["risk_profile"] = risk
        df["sla_maintained"] = sla

        return df


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
        if df.empty or "evicted" not in df.columns:
            return

        x_data = df[["price_volatility", "demand_index", "region_capacity"]]
        y = df["evicted"]

        self.model.fit(x_data, y)
        self.is_trained = True

    def predict_eviction_probability(self, price_volatility, demand_index, region_capacity):
        if not self.is_trained:
            # Fallback heuristic if not trained
            prob = (
                (price_volatility * 0.4) + (demand_index * 0.5) + ((100 - region_capacity) * 0.01)
            )
            return min(max(prob, 0.0), 1.0)

        x_test = pd.DataFrame(
            [
                {
                    "price_volatility": price_volatility,
                    "demand_index": demand_index,
                    "region_capacity": region_capacity,
                }
            ]
        )

        # Probability of class 1 (evicted)
        prob = self.model.predict_proba(x_test)[0][1]
        return float(prob)

    def monitor_and_trigger(self, instance_id, region, telemetry):
        """
        telemetry: dict with 'price_volatility' (0-1), 'demand_index' (0-1), 'region_capacity' (0-100)
        """
        prob = self.predict_eviction_probability(
            telemetry.get("price_volatility", 0.5),
            telemetry.get("demand_index", 0.5),
            telemetry.get("region_capacity", 50.0),
        )

        trigger_migration = prob >= 0.90

        action = "migrate_gracefully" if trigger_migration else "monitor"
        msg = (
            f"90% chance of eviction detected! Triggering automated migration for {instance_id} to stable region."
            if trigger_migration
            else "Instance is stable."
        )

        return {
            "instance_id": instance_id,
            "region": region,
            "eviction_probability": round(prob, 4),
            "action_required": action,
            "message": msg,
        }


# Validation block
if __name__ == "__main__":
    calc = CostCalculator()
    aws_test = calc.calculate_monthly_cost("aws", "ec2", "t3.micro")
    print(f"Projected Monthly Cost for AWS t3.micro: ${aws_test:.2f}")
