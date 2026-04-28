import subprocess
import json

def check_azure_status():
    """Checks if the user is authenticated via Azure CLI."""
    try:
        # Silently try to get an access token
        result = subprocess.run(
            ["az", "account", "get-access-token", "--output", "json"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        return {
            "status": "healthy",
            "message": "Authenticated",
            "expiry": data.get("expiresOn", "N/A"),
            "tenant": data.get("tenant", "N/A")
        }
    except subprocess.CalledProcessError:
        return {"status": "expired", "message": "Session Expired / Not Logged In"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
