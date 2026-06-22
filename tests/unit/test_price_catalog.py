from reaper.collectors.prices.azure import AZURE_RETAIL_SERVICE_NAMES
from reaper.collectors.prices.catalog import normalize_price_record, query_catalog_prices


def test_normalize_azure_api_record():
    raw = {
        "armSkuName": "Standard_D4s_v5",
        "serviceName": "Virtual Machines",
        "armRegionName": "eastus",
        "retailPrice": 0.367,
        "unitOfMeasure": "1 Hour",
        "productName": "Virtual Machines Dsv5 Series Linux",
    }
    result = normalize_price_record(raw, "azure")
    assert result is not None
    assert result["sku"] == "Standard_D4s_v5"
    assert result["region"] == "eastus"
    assert result["service"] == "Virtual Machines"
    assert result["hourly_price"] == 0.367


def test_normalize_aws_api_record():
    raw = {
        "skuName": "t3.micro",
        "serviceName": "Virtual Machines",
        "armRegionName": "us-east-1",
        "retailPrice": 0.0104,
        "unitOfMeasure": "1 Hour",
    }
    result = normalize_price_record(raw, "aws")
    assert result is not None
    assert result["sku"] == "t3.micro"
    assert result["price"] == 0.0104


def test_normalize_skips_error_entries():
    assert normalize_price_record({"sku": "x", "price": 1, "error": "not found"}, "azure") is None


def test_query_catalog_prices_pagination_shape():
    sample = [
        {
            "sku": "Standard_B2s",
            "name": "Standard_B2s",
            "service": "Virtual Machines",
            "region": "eastus",
            "price": 0.05,
            "rate": 0.05,
            "hourly_price": 0.05,
            "monthly_price": 36.5,
            "description": "",
            "provider": "azure",
        },
        {
            "sku": "Standard_D4s_v5",
            "name": "Standard_D4s_v5",
            "service": "Virtual Machines",
            "region": "westus2",
            "price": 0.36,
            "rate": 0.36,
            "hourly_price": 0.36,
            "monthly_price": 262.8,
            "description": "",
            "provider": "azure",
        },
    ]

    from reaper.collectors.prices import catalog as catalog_module

    catalog_module._CATALOG_CACHE["price_catalog_azure"] = (catalog_module.time.time(), sample)
    catalog_module._WARM_STATUS["azure"] = "ready"
    catalog_module._WARM_META["azure"] = {"count": len(sample), "source": "test"}

    result = query_catalog_prices("azure", page=1, per_page=1, search="", sort_by="sku-asc")
    assert result["total"] == 2
    assert len(result["prices"]) == 1
    assert result["page"] == 1
    assert result["total_pages"] == 2


def test_azure_catalog_filters_use_exact_service_list(monkeypatch):
    from reaper.collectors.prices.catalog import get_catalog_filters

    prices = [
        {
            "sku": "Standard_D4s_v5",
            "service": "Virtual Machines",
            "region": "eastus",
            "price": 0.36,
        },
    ]

    monkeypatch.setattr(
        "reaper.collectors.prices.catalog.get_catalog_prices",
        lambda provider: prices,
    )

    filters = get_catalog_filters("azure")
    assert filters["services"] == AZURE_RETAIL_SERVICE_NAMES
    assert filters["regions"] == ["eastus"]
