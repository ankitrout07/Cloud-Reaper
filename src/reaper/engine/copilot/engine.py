from __future__ import annotations

# src/reaper/engine/copilot_engine.py
import copy
import os
import re
import threading
import warnings

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from reaper.engine.copilot.schemas import OptimizationBlueprintSchema
from reaper.engine.core.calculator import CostCalculator

# Suppress EOL warnings from google-auth if any
warnings.filterwarnings("ignore", category=FutureWarning, module="google.auth")
warnings.filterwarnings("ignore", category=FutureWarning, module="google.oauth2")


DOWNGRADE_PATHS = {
    "aws": {
        "compute": ["m5.large", "t3.medium", "t3.small", "t3.micro"],
        "database": ["db.m5.large", "db.t3.medium", "db.t3.small", "db.t3.micro"],
        "storage": ["gp3_per_gb_month"],
    },
    "azure": {
        "compute": ["standard_d4s_v5", "standard_d2s_v5", "standard_d2s_v3", "standard_b2s"],
        "paas": ["app_service_plan_premiumv3_p1v3", "sql_database_serverless_s0"],
        "database": ["standard_e2_v5", "sql_database_serverless_s0"],
        "storage": ["premium_ssd_p6_64gb", "standard_hdd_s4_32gb"],
    },
    "gcp": {
        "compute": ["n2-standard-2", "e2-standard-2"],
        "database": ["db-custom-2-7680", "db-f1-micro"],
        "storage": ["gcs_standard"],
    },
}


class KnapsackCopilotEngine:
    def __init__(self):
        # Use Gemini cloud API
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "CRITICAL: GEMINI_API_KEY environment variable is missing from runtime context."
            )
        self.client = genai.Client(api_key=api_key)
        self.model_identity = "gemini-2.5-flash"
        self.generation_backend = None
        
        self._cache: dict[tuple[str, str, float], OptimizationBlueprintSchema] = {}
        self._cache_lock = threading.Lock()
        self.calculator = CostCalculator()

    def _calculate_component_cost(
        self, provider: str, service_type: str, sku: str, quantity: int, region: str = "eastus"
    ) -> float:
        """
        Looks up the monthly cost for a given infrastructure component using:
        1. RegionPriceCache SQL table.
        2. CostCalculator (price_book.yaml).
        3. Local high-fidelity fallback matrix.
        """
        prov = provider.lower().strip()
        sku_clean = sku.strip()
        cat = service_type.lower().strip()

        # Normalize category
        if prov == "aws":
            if "compute" in cat or "vm" in cat or "instance" in cat:
                cat = "ec2"
            elif "storage" in cat or "disk" in cat or "ebs" in cat:
                cat = "ebs"
        elif prov == "azure":
            if "compute" in cat or "vm" in cat:
                cat = "compute"
            elif "storage" in cat or "disk" in cat:
                cat = "storage"
            elif "network" in cat:
                cat = "networking"
            elif (
                "paas" in cat
                or "db" in cat
                or "sql" in cat
                or "postgres" in cat
                or "database" in cat
            ):
                cat = "paas"

        # 1. DB Query Block using RegionPriceCache
        try:
            from reaper.engine.models.resources import RegionPriceCache, SessionLocal

            db = SessionLocal()
            db_record = (
                db.query(RegionPriceCache)
                .filter(RegionPriceCache.region_name == region)
                .filter(
                    (RegionPriceCache.sku_id.ilike(sku_clean))
                    | (RegionPriceCache.sku_id.ilike(f"%{sku_clean}%"))
                )
                .first()
            )
            if db_record:
                hourly_rate = float(db_record.price)
                db.close()
                # SQL region_price_cache always stores hourly values, normalize to monthly hours (730)
                return hourly_rate * 730 * quantity
            db.close()
        except Exception:
            pass

        # 2. Check CostCalculator (price_book.yaml)
        try:
            prov_prices = self.calculator.prices.get("providers", {}).get(prov, {})
            cat_prices = prov_prices.get(cat, {})
            matched_rate = None
            for k, val in cat_prices.items():
                if k.lower() == sku_clean.lower():
                    matched_rate = float(val)
                    break

            if matched_rate is not None:
                is_storage_type = (
                    cat in ["storage", "disk", "ebs"] or "per_gb_month" in sku_clean.lower()
                )
                if is_storage_type:
                    return matched_rate * quantity
                return matched_rate * 730 * quantity
        except Exception:
            pass

        # 3. Dynamic Local fallback matrix
        sku_lower = sku_clean.lower()
        fallback_rates = {
            "standard_d2s_v5": 0.096,
            "standard_d2s_v3": 0.096,
            "standard_b2s": 0.0416,
            "standard_d4s_v5": 0.192,
            "standard_e2_v5": 0.130,
            "standard_sig_v5": 0.096,
            "blob_hot": 0.020,
            "premium_ssd_p6_64gb": 5.89,
            "standard_hdd_s4_32gb": 1.54,
            "t3.micro": 0.0104,
            "t3.small": 0.0208,
            "t3.medium": 0.0416,
            "m5.large": 0.096,
            "gp3_per_gb_month": 0.08,
            "s3_standard": 0.023,
            "e2-standard-2": 0.067,
            "n2-standard-2": 0.097,
            "gcs_standard": 0.020,
        }

        rate = fallback_rates.get(sku_lower)
        if rate is not None:
            is_storage_type = cat in ["storage", "disk", "ebs"] or "per_gb_month" in sku_lower
            if is_storage_type and rate > 0.5:
                return rate * quantity
            return rate * 730 * quantity

        # Semantic fallback by category
        if "compute" in cat or "vm" in cat:
            rate = 0.0416 if prov == "aws" else (0.067 if prov == "gcp" else 0.096)
        elif "db" in cat or "sql" in cat or "postgres" in cat:
            rate = 0.080 if prov == "aws" else (0.100 if prov == "gcp" else 0.130)
        elif "storage" in cat or "disk" in cat or "ebs" in cat:
            return 0.020 * quantity
        else:
            rate = 0.010

        return rate * 730 * quantity

    def _downgrade_sku(self, provider: str, service_type: str, current_sku: str) -> str | None:
        prov = provider.lower().strip()
        cat = service_type.lower().strip()

        # Normalize category
        if prov == "aws":
            if "compute" in cat or "vm" in cat or "instance" in cat:
                cat = "compute"
            elif "storage" in cat or "disk" in cat or "ebs" in cat:
                cat = "storage"
            elif "db" in cat or "database" in cat or "rds" in cat:
                cat = "database"
        elif prov == "azure":
            if "compute" in cat or "vm" in cat:
                cat = "compute"
            elif "storage" in cat or "disk" in cat:
                cat = "storage"
            elif (
                "paas" in cat
                or "db" in cat
                or "sql" in cat
                or "postgres" in cat
                or "database" in cat
            ):
                cat = "paas"
        elif prov == "gcp":
            if "compute" in cat or "vm" in cat:
                cat = "compute"
            elif "storage" in cat or "disk" in cat:
                cat = "storage"
            elif "db" in cat or "database" in cat or "sql" in cat:
                cat = "database"

        path = DOWNGRADE_PATHS.get(prov, {}).get(cat, [])
        if not path:
            return None

        current_sku_lower = current_sku.lower().strip()
        try:
            idx = -1
            for i, sku in enumerate(path):
                if sku.lower() == current_sku_lower:
                    idx = i
                    break
            if idx != -1 and idx < len(path) - 1:
                return path[idx + 1]
        except Exception:
            pass

        # Try substring lookup
        for idx, sku in enumerate(path[:-1]):
            if sku.lower() in current_sku_lower or current_sku_lower in sku.lower():
                return path[idx + 1]

        return None

    def _get_pricing_context_sheet(self, provider: str) -> str:
        """Generates a grounded price cheat sheet to insert into GenAI instructions."""
        prov = provider.lower().strip()
        lines = [
            f"GROUNDED PRICING CHEAT SHEET FOR {prov.upper()}:",
            "Use these exact SKU sizes and their monthly rates to align with the budget limit.",
            "",
        ]

        known_skus = []
        if prov == "aws":
            known_skus = [
                "t3.micro",
                "t3.small",
                "t3.medium",
                "m5.large",
                "gp3_per_gb_month",
                "s3_standard",
            ]
        elif prov == "azure":
            known_skus = [
                "standard_d2s_v3",
                "standard_b2s",
                "premium_ssd_p6_64gb",
                "standard_hdd_s4_32gb",
                "unassociated_ip",
                "idle_load_balancer",
                "application_gateway_waf_v2",
                "app_service_plan_premiumv3_p1v3",
                "sql_database_serverless_s0",
                "standard_d2s_v5",
                "standard_d4s_v5",
                "standard_e2_v5",
                "standard_sig_v5",
                "blob_hot",
            ]
        elif prov == "gcp":
            known_skus = [
                "e2-standard-2",
                "n2-standard-2",
                "gcs_standard",
                "db-custom-2-7680",
                "db-f1-micro",
            ]

        db_prices = {}
        try:
            from reaper.engine.models.resources import RegionPriceCache, SessionLocal

            db = SessionLocal()
            for sku in known_skus:
                record = (
                    db.query(RegionPriceCache)
                    .filter(
                        RegionPriceCache.region_name == "eastus",
                        (RegionPriceCache.sku_id.ilike(sku))
                        | (RegionPriceCache.sku_id.ilike(f"%{sku}%")),
                    )
                    .first()
                )
                if record:
                    db_prices[sku] = float(record.price) * 730
            db.close()
        except Exception:
            pass

        for sku in known_skus:
            if sku not in db_prices:
                db_prices[sku] = self._calculate_component_cost(prov, "compute", sku, 1)

        lines.append("| SKU / Resource | Monthly Cost (Quantity = 1) |")
        lines.append("| --- | --- |")
        for sku, monthly_cost in db_prices.items():
            lines.append(f"| {sku} | ${monthly_cost:.2f}/month |")
        lines.append("")
        return "\n".join(lines)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3), reraise=True
    )
    def compile_max_performance_infrastructure(
        self, cloud_provider: str, user_intent: str, budget_limit: float
    ) -> OptimizationBlueprintSchema:
        """Calculates and generates the maximum efficiency infrastructure stack strictly bounded by financial limits."""
        cache_key = (
            cloud_provider.lower().strip(),
            user_intent.lower().strip(),
            float(budget_limit),
        )

        with self._cache_lock:
            if cache_key in self._cache:
                return copy.deepcopy(self._cache[cache_key])

        # Generate grounding cheat sheet
        pricing_cheat_sheet = self._get_pricing_context_sheet(cloud_provider)

        system_rules = (
            f"You are the Core FinOps Intelligence Engine for Cloud-Reaper.\n"
            f"Target Provider: {cloud_provider.upper()}\n"
            f"Maximum Absolute Budget Boundary: ${budget_limit:.2f}/month.\n\n"
            f"CRITICAL OPERATIONAL RULES:\n"
            f"1. Maximize system performance, throughput, availability, and capacity for the given workload intent.\n"
            f"2. calculated_total_cost MUST be less than or equal to ${budget_limit:.2f}/month. Never exceed this limit.\n"
            f"3. Do not minimize cost blindly; spend up to the budget limit if it translates into maximum compute performance.\n"
            f"4. Ensure valid architectural practices (e.g., do not omit load balancers or base networks for scale-out designs).\n"
            f"5. All generated Terraform components MUST contain production tagging configurations: Env='sandbox' and Owner='ankit'.\n"
            f"6. Return strictly valid JSON adhering perfectly to the required output schema contract.\n\n"
            f"{pricing_cheat_sheet}"
        )

        # Use Gemini cloud API
        response = self.client.models.generate_content(
            model=self.model_identity,
            contents=f"Workload Goal Specification: {user_intent}",
            config=types.GenerateContentConfig(
                system_instruction=system_rules,
                response_mime_type="application/json",
                response_schema=OptimizationBlueprintSchema,
                temperature=0.1,
            ),
        )
        result = OptimizationBlueprintSchema.model_validate_json(response.text)

        # Recalculate & scale-down heuristic correction loop
        iteration = 0
        max_iterations = 20
        while iteration < max_iterations:
            total_recalculated_cost = 0.0
            component_costs = []

            for comp in result.infrastructure_components:
                cost = self._calculate_component_cost(
                    provider=cloud_provider,
                    service_type=comp.service_type,
                    sku=comp.sku_size,
                    quantity=comp.quantity,
                )
                comp.monthly_cost = cost
                total_recalculated_cost += cost
                component_costs.append((cost, comp))

            result.calculated_total_cost = round(total_recalculated_cost, 2)

            if total_recalculated_cost <= budget_limit:
                break

            # Sort by total cost descending to downgrade the most expensive driver
            component_costs.sort(key=lambda x: x[0], reverse=True)
            downgraded_any = False

            for cost, comp in component_costs:
                if comp.quantity > 1:
                    old_qty = comp.quantity
                    new_qty = old_qty - 1

                    # Regex replacement of count in Terraform HCL
                    old_hcl = result.production_terraform_hcl
                    new_hcl = re.sub(rf"count\s*=\s*{old_qty}\b", f"count = {new_qty}", old_hcl)

                    comp.quantity = new_qty
                    result.production_terraform_hcl = new_hcl
                    downgraded_any = True
                    break
                old_sku = comp.sku_size
                new_sku = self._downgrade_sku(cloud_provider, comp.service_type, old_sku)
                if new_sku:
                    # Regex replacement of SKU in Terraform HCL
                    old_hcl = result.production_terraform_hcl
                    new_hcl = re.sub(re.escape(old_sku), new_sku, old_hcl, flags=re.IGNORECASE)

                    comp.sku_size = new_sku
                    result.production_terraform_hcl = new_hcl
                    downgraded_any = True
                    break

            if not downgraded_any:
                break

            iteration += 1

        with self._cache_lock:
            # Evict oldest entry if cache grows too large
            while len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = copy.deepcopy(result)

        return result


class AnomalyTriager:
    def __init__(self):
        # Use Gemini cloud API
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "CRITICAL: GEMINI_API_KEY environment variable is missing from runtime context."
            )
        self.client = genai.Client(api_key=api_key)
        self.model_identity = "gemini-2.5-flash"
        self.generation_backend = None

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3), reraise=True
    )
    def generate_triage_playbook(self, service_name: str, cost: float, deviation: str) -> str:
        """Analyzes a spend anomaly and generates a human-readable mitigation playbook."""
        system_rules = (
            "You are the FinOps AI Triage Assistant for Cloud-Reaper.\n"
            "Your job is to analyze cloud infrastructure spending anomalies and provide a concise, "
            "actionable mitigation playbook.\n"
            "Output MUST be in HTML format (use standard tags like <strong>, <ul>, <li>, <a>) "
            "and include a simulated link to apply a Terraform fix. "
            "Do NOT include markdown backticks (e.g., ```html). Just return the raw HTML string.\n"
            "Keep it under 3-4 short sentences before the actionable link.\n"
            "Example format:\n"
            "<p>This spike in <strong>{Service Name}</strong> was likely caused by an un-optimized NAT Gateway egress loop.</p>"
            "<p><a href='#' class='text-cyan-400 font-bold underline cursor-pointer'>Click here to apply the Terraform fix</a></p>"
        )

        prompt = (
            f"Anomaly Detected:\n"
            f"Service: {service_name}\n"
            f"Recent Cost: ${cost:.2f}\n"
            f"Deviation vs Average: {deviation}\n\n"
            f"Analyze this infrastructure change and generate a brief mitigation playbook in HTML."
        )

        try:
            # Use Gemini cloud API
            response = self.client.models.generate_content(
                model=self.model_identity,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_rules,
                    temperature=0.4,
                ),
            )
            text = str(response.text).strip()
            
            # Clean up markdown formatting if present
            if text.startswith("```html"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            return str(text).strip()
        except Exception as e:
            return f"<p class='text-rose-500'>Error generating AI triage: {e!s}</p>"
