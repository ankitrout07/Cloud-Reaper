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
