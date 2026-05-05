import json
import subprocess


def check_azure_status():
    """Checks if the user is authenticated via Azure CLI or Service Principal."""
    import os

    # Check for Service Principal first (as it takes priority in DefaultAzureCredential)
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    tenant_id = os.getenv("AZURE_TENANT_ID")

    if client_id and client_secret and tenant_id:
        return {
            "status": "healthy",
            "message": "Connected: Service Principal (SP)",
            "expiry": "Persistent",
            "tenant": tenant_id,
        }

    try:
        # Fallback to Azure CLI
        result = subprocess.run(
            ["az", "account", "get-access-token", "--output", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return {
            "status": "healthy",
            "message": "Connected: Azure CLI",
            "expiry": data.get("expiresOn", "N/A"),
            "tenant": data.get("tenant", "N/A"),
        }
    except subprocess.CalledProcessError:
        return {"status": "expired", "message": "Disconnected: Login Required"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
