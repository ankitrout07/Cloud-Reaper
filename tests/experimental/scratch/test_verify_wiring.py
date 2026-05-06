import json
import subprocess
from pathlib import Path

from reaper.collectors.azure_collector import AzureCollector
from reaper.engine.schema import validate_scan_result


def test_verify_wiring():
    az = AzureCollector()

    # Basic API check
    assert hasattr(az, 'get_live_prices')
    assert hasattr(az, 'fast_scan')

    # Deep schema verification of the Go-Python bridge
    go_binary = Path(__file__).resolve().parent.parent.parent.parent / "src" / "engine-go" / "reaper-engine"

    if go_binary.exists():
        # Test the prices mode JSON schema handoff
        result = subprocess.run(
            [str(go_binary), "--mode", "prices"], 
            capture_output=True, 
            text=True, 
            check=False
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Validate that the Go Engine's JSON matches our formalized Python schema
            assert validate_scan_result(data), "Go Engine JSON output does not match Python schema!"
            assert "prices" in data, "Prices array missing from Go Engine output."
