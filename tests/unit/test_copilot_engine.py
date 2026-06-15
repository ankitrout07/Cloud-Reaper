import os
from unittest.mock import MagicMock, patch

import pytest

from reaper.engine.copilot.engine import KnapsackCopilotEngine
from reaper.engine.copilot.schemas import ItemizedComponent, OptimizationBlueprintSchema

pytestmark = pytest.mark.usefixtures("mock_gemini_env")


@pytest.fixture
def mock_gemini_env():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-api-key"}), \
         patch("reaper.engine.models.resources.SessionLocal") as mock_session:
        mock_db = MagicMock()
        # Mock query chain: query().filter().filter().first() -> None
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        mock_session.return_value = mock_db
        yield


def test_copilot_engine_initialization():
    engine = KnapsackCopilotEngine()
    assert engine.calculator is not None
    assert engine._cache_lock is not None
    assert engine._cache == {}


def test_calculate_component_cost():
    engine = KnapsackCopilotEngine()

    # 1. Test fallback rate calculation for azure compute
    cost = engine._calculate_component_cost("azure", "compute", "standard_d2s_v5", 2)
    # standard_d2s_v5 fallback rate is 0.096/hr. 0.096 * 730 * 2 = 140.16
    assert abs(cost - 140.16) < 0.01

    # 2. Test fallback rate calculation for aws compute
    cost_aws = engine._calculate_component_cost("aws", "compute", "t3.micro", 1)
    # t3.micro fallback rate is 0.0104/hr. 0.0104 * 730 = 7.592
    assert abs(cost_aws - 7.592) < 0.01

    # 3. Test storage monthly rates (e.g. premium_ssd_p6_64gb)
    cost_storage = engine._calculate_component_cost("azure", "storage", "premium_ssd_p6_64gb", 3)
    # premium_ssd_p6_64gb fallback is 5.89/month. 5.89 * 3 = 17.67
    assert abs(cost_storage - 17.67) < 0.01


def test_downgrade_sku():
    engine = KnapsackCopilotEngine()

    # Test valid Azure compute downgrades
    next_sku = engine._downgrade_sku("azure", "compute", "standard_d4s_v5")
    assert next_sku == "standard_d2s_v5"

    next_sku = engine._downgrade_sku("azure", "compute", "standard_d2s_v5")
    assert next_sku == "standard_d2s_v3"

    next_sku = engine._downgrade_sku("azure", "compute", "standard_b2s")
    assert next_sku is None  # smallest SKU

    # Test invalid category / SKU
    assert engine._downgrade_sku("azure", "compute", "unknown_sku") is None


def test_get_pricing_context_sheet():
    engine = KnapsackCopilotEngine()
    sheet = engine._get_pricing_context_sheet("azure")

    assert "GROUNDED PRICING CHEAT SHEET FOR AZURE" in sheet
    assert "standard_d2s_v5" in sheet
    assert "premium_ssd_p6_64gb" in sheet


def test_cache_deep_copy_and_eviction():
    engine = KnapsackCopilotEngine()

    # Pre-populate cache with a mock schema
    blueprint = OptimizationBlueprintSchema(
        system_architecture_overview="Mock Architecture",
        max_budget_boundary=1000.0,
        calculated_total_cost=200.0,
        efficiency_index_score=85,
        infrastructure_components=[
            ItemizedComponent(
                name="web-vm",
                service_type="compute",
                sku_size="standard_d2s_v5",
                quantity=1,
                monthly_cost=70.08,
                perf_factor="Standard compute",
            )
        ],
        production_terraform_hcl='resource "azurerm_virtual_machine" "web" { count = 1 }',
    )

    # Put in cache
    engine._cache[("azure", "test-intent", 1000.0)] = blueprint

    # Retrieve from cache and verify deep copy
    retrieved = engine.compile_max_performance_infrastructure("azure", "test-intent", 1000.0)
    assert retrieved.calculated_total_cost == 200.0

    # Mutate retrieved copy and verify cache remains unaffected
    retrieved.calculated_total_cost = 500.0
    assert engine._cache[("azure", "test-intent", 1000.0)].calculated_total_cost == 200.0

    # Verify cache eviction at 128 elements
    engine._cache.clear()
    for i in range(128):
        engine._cache[(f"azure_{i}", "intent", 100.0)] = blueprint

    # Trigger compiler for new key (which forces eviction since len >= 128)
    with patch.object(engine.client.models, "generate_content") as mock_gen:
        mock_response = MagicMock()
        mock_response.text = blueprint.model_dump_json()
        mock_gen.return_value = mock_response

        engine.compile_max_performance_infrastructure("azure", "new-intent", 500.0)
        # Verify size remains <= 128
        assert len(engine._cache) == 128


@patch("google.genai.Client")
def test_scale_down_correction_loop(_mock_client_cls):
    engine = KnapsackCopilotEngine()

    # Setup mock response containing resources that BREACH the budget boundary
    # Budget = 100.0
    # Recalculated cost will be:
    # VM standard_d4s_v5 (0.192 * 730 * 2 = 280.32) -> exceeds budget of 100.0
    initial_hcl = (
        'resource "azurerm_virtual_machine" "vm" {\n  count = 2\n  size = "Standard_D4s_v5"\n}'
    )

    blueprint = OptimizationBlueprintSchema(
        system_architecture_overview="High capacity VM",
        max_budget_boundary=100.0,
        calculated_total_cost=280.32,
        efficiency_index_score=90,
        infrastructure_components=[
            ItemizedComponent(
                name="app-vm",
                service_type="compute",
                sku_size="standard_d4s_v5",
                quantity=2,
                monthly_cost=280.32,
                perf_factor="High performance compute VM",
            )
        ],
        production_terraform_hcl=initial_hcl,
    )

    mock_response = MagicMock()
    mock_response.text = blueprint.model_dump_json()
    engine.client.models.generate_content = MagicMock(return_value=mock_response)

    # Compile with budget_limit = 100.0
    final_blueprint = engine.compile_max_performance_infrastructure("azure", "web server", 100.0)

    # Recalculation & scale-down:
    # 1. 2 x standard_d4s_v5 = 280.32 (> 100) -> downgrade quantity: count=2 to count=1 (1 x standard_d4s_v5 = 140.16)
    # 2. 1 x standard_d4s_v5 = 140.16 (> 100) -> downgrade SKU: standard_d4s_v5 to standard_d2s_v5 (1 x standard_d2s_v5 = 70.08)
    # 3. 1 x standard_d2s_v5 = 70.08 (<= 100) -> success!

    assert final_blueprint.calculated_total_cost <= 100.0
    comp = final_blueprint.infrastructure_components[0]
    assert comp.quantity == 1
    assert comp.sku_size == "standard_d2s_v5"
    assert abs(comp.monthly_cost - 70.08) < 0.01

    # Verify HCL has been updated with new count and SKU
    assert "count = 1" in final_blueprint.production_terraform_hcl
    assert "standard_d2s_v5" in final_blueprint.production_terraform_hcl.lower()
    assert "Standard_D4s_v5" not in final_blueprint.production_terraform_hcl
