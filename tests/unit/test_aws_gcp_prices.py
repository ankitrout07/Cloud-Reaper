from reaper.collectors.prices.aws import AWSPriceClient
from reaper.collectors.prices.gcp import GCPPriceClient


def test_aws_price_client_init():
    client = AWSPriceClient()
    assert client.URL == "https://instances.vantage.sh/instances.json"
    assert hasattr(client, "get_live_prices")


def test_gcp_price_client_init():
    client = GCPPriceClient()
    assert (
        client.URL
        == "https://raw.githubusercontent.com/doitintl/gcpinstances.info/master/public/data/pricing.json"
    )
    assert hasattr(client, "get_live_prices")
