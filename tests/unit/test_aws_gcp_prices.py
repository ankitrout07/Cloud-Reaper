from reaper.collectors.aws_prices import AWSPriceClient
from reaper.collectors.gcp_prices import GCPPriceClient


def test_aws_price_client_init():
    client = AWSPriceClient()
    assert client.URL == "https://ec2instances.info/instances.json"
    assert hasattr(client, "get_live_prices")


def test_gcp_price_client_init():
    client = GCPPriceClient()
    assert (
        client.URL
        == "https://raw.githubusercontent.com/doitintl/gcpinstances.info/master/public/data/pricing.json"
    )
    assert hasattr(client, "get_live_prices")
