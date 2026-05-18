import os

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient


def fetch_azure_logs(resource_id=None):
    try:
        client = LogsQueryClient(DefaultAzureCredential())
        workspace_id = os.getenv("AZURE_WORKSPACE_ID")
        if not workspace_id:
            return ["Error: Workspace ID not configured in .env. Cannot stream logs."]

        if resource_id:
            query = f"AzureActivity | where ResourceId == '{resource_id}' | take 10"
        else:
            # Query to fetch the last few logs
            query = "AzureActivity | take 10"

        response = client.query_workspace(workspace_id, query, timespan=None)
        if response.tables and response.tables[0].rows:
            return [str(row) for row in response.tables[0].rows]
        return ["No recent logs found."]
    except Exception as e:
        return [f"Log Fetch Error: {e!s}"]
