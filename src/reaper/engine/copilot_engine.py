# src/reaper/engine/copilot_engine.py
import os
import warnings

from google import genai
from google.genai import types

from reaper.engine.copilot_schemas import OptimizationBlueprintSchema

# Suppress EOL warnings from google-auth if any
warnings.filterwarnings("ignore", category=FutureWarning, module="google.auth")
warnings.filterwarnings("ignore", category=FutureWarning, module="google.oauth2")


class KnapsackCopilotEngine:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "CRITICAL: GEMINI_API_KEY environment variable is missing from runtime context."
            )
        self.client = genai.Client(api_key=api_key)
        self.model_identity = "gemini-2.5-flash"
        self._cache = {}

    def compile_max_performance_infrastructure(
        self, cloud_provider: str, user_intent: str, budget_limit: float
    ) -> OptimizationBlueprintSchema:
        """Calculates and generates the maximum efficiency infrastructure stack strictly bounded by financial limits."""

        cache_key = (
            cloud_provider.lower().strip(),
            user_intent.lower().strip(),
            float(budget_limit),
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

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
            f"6. Return strictly valid JSON adhering perfectly to the required output schema metadata contract."
        )

        response = self.client.models.generate_content(
            model=self.model_identity,
            contents=f"Workload Goal Specification: {user_intent}",
            config=types.GenerateContentConfig(
                system_instruction=system_rules,
                response_mime_type="application/json",
                response_schema=OptimizationBlueprintSchema,
                temperature=0.1,  # Enforces rigid structural and mathematical compliance
            ),
        )

        result = OptimizationBlueprintSchema.model_validate_json(response.text)

        # Evict old entries if cache grows too large
        if len(self._cache) >= 128:
            self._cache.pop(next(iter(self._cache)))

        self._cache[cache_key] = result
        return result
