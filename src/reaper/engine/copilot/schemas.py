# src/reaper/engine/copilot_schemas.py

from pydantic import BaseModel, Field


class ItemizedComponent(BaseModel):
    name: str = Field(..., description="Logical identification of resource component.")
    service_type: str = Field(
        ..., description="Exact Infrastructure-as-Code identifier resource type."
    )
    sku_size: str = Field(
        ..., description="Optimized high-performance SKU selected under boundary constraints."
    )
    quantity: int = Field(..., description="Total integer count of deployed instances.")
    monthly_cost: float = Field(
        ..., description="Aggregated monthly resource financial impact in USD."
    )
    perf_factor: str = Field(
        ..., description="Technical justification tracking performance maximization."
    )


class OptimizationBlueprintSchema(BaseModel):
    system_architecture_overview: str = Field(
        ..., description="High-level systemic execution summary."
    )
    max_budget_boundary: float = Field(
        ..., description="The user-defined maximum absolute budget limit."
    )
    calculated_total_cost: float = Field(
        ..., description="Total aggregated monthly cost. Must be <= max_budget_boundary."
    )
    efficiency_index_score: int = Field(
        ..., description="Performance throughput value score per dollar spent (1-100)."
    )
    infrastructure_components: list[ItemizedComponent] = Field(
        ..., description="Optimized component manifest."
    )
    production_terraform_hcl: str = Field(
        ..., description="Valid, production-ready, deployment-grade Terraform code block."
    )
