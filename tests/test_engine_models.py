from reaper.engine.models import Resource, CostHistory
import datetime

try:
    from datetime import UTC
except ImportError:
    UTC = datetime.timezone.utc

def test_resource_model_instantiation():
    resource = Resource(
        id="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        name="vm1",
        type="Microsoft.Compute/virtualMachines",
        region="eastus",
        tags={"env": "prod"},
        active=True,
        is_protected=False
    )
    
    assert resource.name == "vm1"
    assert resource.region == "eastus"
    assert resource.tags["env"] == "prod"
    assert resource.active is True
    assert resource.is_protected is False

def test_cost_history_model_instantiation():
    cost = CostHistory(
        resource_id="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        cost=100.50,
        currency="USD",
        cost_type="ACTUAL",
        date=datetime.datetime.now(UTC)
    )
    
    assert cost.cost == 100.50
    assert cost.currency == "USD"
    assert cost.cost_type == "ACTUAL"
