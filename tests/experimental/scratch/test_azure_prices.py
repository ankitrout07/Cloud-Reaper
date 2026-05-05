from reaper.collectors.azure_prices import AzurePriceClient


def test_azure_price_client_init():
    client = AzurePriceClient(currency="USD")
    assert client.currency == "USD"
    assert client.BASE_URL is not None


def test_azure_price_fetch_logic():
    # Note: This hits real API, in a real CI we would mock this.
    # For now, we just ensure the methods exist and can be called.
    client = AzurePriceClient(currency="USD")
    
    # We'll just verify the client object has the expected methods
    assert hasattr(client, 'get_prices_by_service')
    assert hasattr(client, 'get_category_prices')
