import os
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

# Define the strict structure for each infrastructure component
class CloudComponent(BaseModel):
    component_type: str = Field(description="The structural category: compute, database, storage, or networking")
    generic_name: str = Field(description="Friendly name, e.g., Managed Kubernetes, Block Storage")
    provider_sku_keyword: str = Field(description="The exact instance type or SKU keyword, e.g., t3.medium, Standard_D2_v5, db-f1-micro")
    quantity: int = Field(description="Number of units needed to satisfy the capacity or high-availability requirements")
    reasoning: str = Field(description="A brief explanation of why this size or resource tier was selected")

# Define the top-level schema contract that the LLM must return
class ArchitectureBlueprint(BaseModel):
    architecture_summary: str = Field(description="High-level overview of how this deployment works")
    components: List[CloudComponent] = Field(description="The precise list of required infrastructure components")
    security_warning: Optional[str] = Field(None, description="Any critical architectural or security warnings for this stack")

class AIArchitectManager:
    def __init__(self):
        # Gracefully pull the API key from your environment setup
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)

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
                {"role": "user", "content": user_prompt}
            ],
            response_format=ArchitectureBlueprint,
        )
        return response.choices[0].message.parsed
