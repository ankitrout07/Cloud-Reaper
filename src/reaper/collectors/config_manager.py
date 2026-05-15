import os
from pathlib import Path


def save_config(sub_id, tenant_id=None, client_id=None, client_secret=None):
    """Saves Azure credentials to a .env file and updates environment variables."""
    try:
        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = env_path.read_text().splitlines(keepends=True)

        keys_to_update = {"AZURE_SUBSCRIPTION_ID": sub_id}
        if tenant_id:
            keys_to_update["AZURE_TENANT_ID"] = tenant_id
        if client_id:
            keys_to_update["AZURE_CLIENT_ID"] = client_id
        if client_secret:
            keys_to_update["AZURE_CLIENT_SECRET"] = client_secret

        new_lines = _process_env_lines(lines, keys_to_update)
        env_path.write_text("".join(new_lines))

        _update_os_environ(keys_to_update)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def _process_env_lines(lines, keys_to_update):
    """Processes existing .env lines and updates or appends new keys."""
    new_lines = []
    keys_handled = set()

    for line in lines:
        handled = False
        for key, value in keys_to_update.items():
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                keys_handled.add(key)
                handled = True
                break
        if not handled:
            new_lines.append(line)

    for key, value in keys_to_update.items():
        if key not in keys_handled:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")

    return new_lines


def _update_os_environ(keys_to_update):
    """Updates the current process environment variables."""
    for key, value in keys_to_update.items():
        os.environ[key] = value


def normalize_resource(provider: str, resource: dict) -> dict:
    """Maps provider native objects into a unified Reaper schema."""
    provider = provider.lower()
    if provider == "aws":
        return _normalize_aws_resource(resource)
    if provider == "azure":
        return _normalize_azure_resource(resource)
    if provider == "gcp":
        return _normalize_gcp_resource(resource)
    if provider == "k8s":
        return _normalize_k8s_resource(resource)
    return _normalize_generic_resource(resource)


def _normalize_aws_resource(resource: dict) -> dict:
    tags = {
        item.get("Key"): item.get("Value")
        for item in resource.get("tags", [])
        if isinstance(resource.get("tags", []), list)
    }
    return {
        "id": resource.get("InstanceId") or resource.get("VolumeId") or resource.get("ResourceId"),
        "name": tags.get("Name") or resource.get("InstanceType") or resource.get("id"),
        "type": "ComputeResource" if resource.get("InstanceId") else "StorageResource",
        "region": resource.get("region")
        or resource.get("AvailabilityZone")
        or resource.get("aws_region")
        or "unknown",
        "hourly_cost": float(resource.get("hourly_cost") or resource.get("cost") or 0.0),
        "provider": "aws",
        "metadata": {"raw": resource, "tags": tags},
    }


def _normalize_azure_resource(resource: dict) -> dict:
    return {
        "id": resource.get("id") or resource.get("resource_id") or resource.get("instance_id"),
        "name": resource.get("name") or resource.get("vm_name") or resource.get("instance_name"),
        "type": "ComputeResource"
        if "vm" in (resource.get("type", "").lower())
        else "StorageResource",
        "region": resource.get("region") or resource.get("location") or "unknown",
        "hourly_cost": float(resource.get("hourly_cost") or resource.get("cost") or 0.0),
        "provider": "azure",
        "metadata": resource,
    }


def _normalize_gcp_resource(resource: dict) -> dict:
    return {
        "id": resource.get("id") or resource.get("instance_id") or resource.get("resource_id"),
        "name": resource.get("name")
        or resource.get("display_name")
        or resource.get("instance_name"),
        "type": "ComputeResource"
        if resource.get("machine_type") or resource.get("resource_type") == "compute"
        else "StorageResource",
        "region": resource.get("zone") or resource.get("region") or "unknown",
        "hourly_cost": float(resource.get("hourly_cost") or resource.get("cost") or 0.0),
        "provider": "gcp",
        "metadata": resource,
    }


def _normalize_k8s_resource(resource: dict) -> dict:
    return {
        "id": resource.get("metadata", {}).get("uid") or resource.get("name") or resource.get("id"),
        "name": resource.get("metadata", {}).get("name") or resource.get("name"),
        "type": resource.get("kind") or resource.get("type") or "KubernetesResource",
        "region": resource.get("metadata", {}).get("namespace") or "cluster",
        "hourly_cost": float(resource.get("hourly_cost") or resource.get("cost") or 0.0),
        "provider": "k8s",
        "metadata": resource,
    }


def _normalize_generic_resource(resource: dict) -> dict:
    return {
        "id": resource.get("id") or resource.get("resource_id") or "unknown",
        "name": resource.get("name") or resource.get("display_name") or "unnamed",
        "type": resource.get("type") or "Resource",
        "region": resource.get("region") or resource.get("location") or "unknown",
        "hourly_cost": float(resource.get("hourly_cost") or resource.get("cost") or 0.0),
        "provider": resource.get("provider") or "unknown",
        "metadata": resource,
    }
