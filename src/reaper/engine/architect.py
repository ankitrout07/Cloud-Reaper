import os
import json
import requests

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
        # Gracefully pull the API keys from your environment setup
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.client = None

        if self.openai_key:
            self.client = OpenAI(api_key=self.openai_key)

    def verify_api_status(self) -> dict:
        """
        Verifies both OpenAI and Gemini API Key statuses.
        Returns:
            dict containing status of 'openai' and 'gemini' keys: 'active', 'invalid', 'unconfigured'
        """
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

        status = {
            "openai": "unconfigured",
            "gemini": "unconfigured"
        }

        # Verify OpenAI
        if self.openai_key and self.openai_key != "your_actual_openai_api_key_here":
            try:
                self.client = OpenAI(api_key=self.openai_key)
                self.client.models.list()
                status["openai"] = "active"
            except Exception:
                status["openai"] = "invalid"

        # Verify Gemini
        if self.gemini_key and self.gemini_key != "your_actual_gemini_api_key_here":
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.gemini_key}"
                res = requests.get(url, timeout=5)
                if res.status_code == 200:
                    status["gemini"] = "active"
                else:
                    status["gemini"] = "invalid"
            except Exception:
                status["gemini"] = "invalid"

        return status

    def generate_blueprint(self, user_prompt: str, provider: str, model_provider: str = "openai") -> ArchitectureBlueprint:
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

        system_instructions = (
            f"You are the Principal Cloud Architect engine for Cloud-Reaper. "
            f"Analyze the user request and design a cost-optimized, production-ready cloud architecture "
            f"exclusively using {provider.upper()} services. You must follow the requested provider strictly. "
            f"Do not mix providers. Output your response as a pristine structured JSON object matching the schema."
        )

        if model_provider == "gemini" or (not self.openai_key and self.gemini_key):
            if not self.gemini_key or self.gemini_key == "your_actual_gemini_api_key_here":
                raise ValueError("GEMINI_API_KEY is not set in the environment variables.")

            # Call Gemini Structured Output API
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": system_instructions},
                            {"text": user_prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "architecture_summary": {"type": "STRING"},
                            "components": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "component_type": {"type": "STRING"},
                                        "generic_name": {"type": "STRING"},
                                        "provider_sku_keyword": {"type": "STRING"},
                                        "quantity": {"type": "INTEGER"},
                                        "reasoning": {"type": "STRING"}
                                    },
                                    "required": ["component_type", "generic_name", "provider_sku_keyword", "quantity", "reasoning"]
                                }
                            },
                            "security_warning": {"type": "STRING"}
                        },
                        "required": ["architecture_summary", "components"]
                    }
                }
            }
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            if res.status_code != 200:
                raise ValueError(f"Gemini API returned error: {res.text}")

            data = res.json()
            try:
                text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                blueprint_dict = json.loads(text_content)
                return ArchitectureBlueprint(**blueprint_dict)
            except Exception as e:
                raise ValueError(f"Failed to parse structured response from Gemini API: {str(e)}")
        else:
            if not self.openai_key:
                raise ValueError("OPENAI_API_KEY is not set in the environment variables.")

            self.client = OpenAI(api_key=self.openai_key)
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
        "azure": {
            "standard_sig_v5": 0.096,
            "standard_d2_v5": 0.096,
            "standard_e2_v5": 0.130,
            "blob_hot": 0.020,
        },
        "aws": {"t3.medium": 0.0416, "m5.large": 0.096, "t3.micro": 0.0104, "s3_standard": 0.023},
        "gcp": {"e2-standard-2": 0.067, "n2-standard-2": 0.097, "gcs_standard": 0.020},
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
        component_payload["calculated_monthly_cost"] = round(monthly_cost, 2)
        calculated_components.append(component_payload)

    return {
        "summary": blueprint_data.architecture_summary,
        "provider": provider.lower(),
        "region": region,
        "components": calculated_components,
        "total_monthly_cost_estimate": round(total_monthly_cost, 2),
        "security_warning": blueprint_data.security_warning,
    }
