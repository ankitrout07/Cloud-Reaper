import os

from dotenv import load_dotenv

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS

    _INFLUXDB_AVAILABLE = True
except ImportError:
    _INFLUXDB_AVAILABLE = False

load_dotenv()


class DataPusher:
    def __init__(self):
        self.url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = os.getenv("INFLUXDB_TOKEN")
        self.org = os.getenv("INFLUXDB_ORG")
        self.bucket = os.getenv("INFLUXDB_BUCKET")
        self.write_api = None

        if _INFLUXDB_AVAILABLE and all([self.token, self.org, self.bucket]):
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def push_savings(self, provider, amount):
        if not self.write_api:
            return

        point = (
            Point("cloud_waste")
            .tag("provider", provider)
            .field("potential_savings", float(amount))
            .time(WritePrecision.NS)
        )

        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as e:
            print(f"[!] InfluxDB Push Failed: {e}")

    def close(self):
        if hasattr(self, "client"):
            self.client.close()
