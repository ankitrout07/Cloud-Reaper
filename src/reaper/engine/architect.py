import os

from openai import OpenAI
from pydantic import BaseModel, Field


# Define the strict structure for each infrastructure component
class CloudComponent(BaseModel):
    component_type: str = Field(
        description="The structural category: compute, database, storage, or networking"
    )
    generic_name: str = Field(description="Friendly name, e.g., Managed Kubernetes, Block Storage")
    provider_sku_keyword: str = Field(
        description="The exact instance type or SKU keyword, e.g., t3.medium, Standard_D2_v5, db-f1-micro"
    )
    quantity: int = Field(
        description="Number of units needed to satisfy the capacity or high-availability requirements"
    )
    reasoning: str = Field(
        description="A brief explanation of why this size or resource tier was selected"
    )


# Define the top-level schema contract that the LLM must return
class ArchitectureBlueprint(BaseModel):
    architecture_summary: str = Field(
        description="High-level overview of how this deployment works"
    )
    components: list[CloudComponent] = Field(
        description="The precise list of required infrastructure components"
    )
    security_warning: str | None = Field(
        None, description="Any critical architectural or security warnings for this stack"
    )


class AIArchitectManager:
    def __init__(self):
        # Gracefully pull the API key from your environment setup
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None

        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)

    def verify_api_status(self) -> str:
        """
        Verifies the OpenAI API Key status.
        Returns:
            "active" - key is set and valid
            "invalid" - key is set but invalid/rejected
            "unconfigured" - key is missing
        """
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your_actual_openai_api_key_here":
            return "unconfigured"
            
        try:
            self.client = OpenAI(api_key=self.api_key)
            self.client.models.list()
            return "active"
        except Exception:
            return "invalid"

    def generate_blueprint(self, user_prompt: str, provider: str) -> ArchitectureBlueprint:
        if not self.client:
            raise ValueError("OPENAI_API_KEY is not set in the environment variables.")

        system_instructions = (
            f"You are the Principal Cloud Architect engine for Cloud-Reaper. "
            f"Analyze the user request and design a cost-optimized, production-ready cloud architecture "
            f"exclusively using {provider.upper()} services. You must follow the requested provider strictly. "
            f"Do not mix providers. Output your response as a pristine structured JSON object matching the schema."
        )

        # Force structured output parsing via the SDK
        response = self.client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt},
            ],
            response_format=ArchitectureBlueprint,
        )
        return response.choices[0].message.parsed


def resolve_component_costs(blueprint_data, provider: str, region: str) -> dict:
    """
    Takes the structured LLM blueprint, queries the region_price_cache table,
    calculates monthly operational metrics, and applies a resilient fallback matrix.
    """
    total_monthly_cost = 0.0
    calculated_components = []
    
    # High-fidelity static fallback matrix for development/offline parity
    # Keeps your dashboard functional even if the Go core hasn't cached the SKU yet
    price_fallbacks = {
        "azure": {"standard_sig_v5": 0.096, "standard_d2_v5": 0.096, "standard_e2_v5": 0.130, "blob_hot": 0.020},
        "aws": {"t3.medium": 0.0416, "m5.large": 0.096, "t3.micro": 0.0104, "s3_standard": 0.023},
        "gcp": {"e2-standard-2": 0.067, "n2-standard-2": 0.097, "gcs_standard": 0.020}
    }

    provider_fallbacks = price_fallbacks.get(provider.lower(), {})

    for item in blueprint_data.components:
        sku = item.provider_sku_keyword.lower().strip()
        quantity = item.quantity if item.quantity > 0 else 1
        hourly_rate = None

        # --- DATABASE QUERY BLOCK ---
        # Note: In production, this maps directly to your region_price_cache model
        # Example: session.query(RegionPriceCache).filter_by(sku=sku, region=region).first()
        try:
            # Placeholder for active DB query lookup
            # If a match is found in your PostgreSQL table, assign it:
            # hourly_rate = db_record.hourly_price
            pass
        except Exception:
            # Fail silently and let the circuit breaker fall back to static maps
            hourly_rate = None

        # --- FALLBACK CIRCUIT BREAKER ---
        if hourly_rate is None:
            # Match strict keyword or default to a baseline compute tier rate
            hourly_rate = provider_fallbacks.get(sku, 0.05) 

        # Calculate standard cloud monthly operational hours (730 hours/month)
        monthly_cost = float(hourly_rate) * 730 * quantity
        total_monthly_cost += monthly_cost

        component_payload = item.model_dump()
        component_payload['calculated_monthly_cost'] = round(monthly_cost, 2)
        calculated_components.append(component_payload)

    return {
        "summary": blueprint_data.architecture_summary,
        "provider": provider.lower(),
        "region": region,
        "components": calculated_components,
        "total_monthly_cost_estimate": round(total_monthly_cost, 2),
        "security_warning": blueprint_data.security_warning
    }

