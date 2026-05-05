import os


def save_config(sub_id, tenant_id=None, client_id=None, client_secret=None):
    # Write to a .env file locally
    try:
        env_path = ".env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()

        # Prepare new content
        new_lines = []
        keys_to_update = {"AZURE_SUBSCRIPTION_ID": sub_id}
        if tenant_id:
            keys_to_update["AZURE_TENANT_ID"] = tenant_id
        if client_id:
            keys_to_update["AZURE_CLIENT_ID"] = client_id
        if client_secret:
            keys_to_update["AZURE_CLIENT_SECRET"] = client_secret

        keys_handled = set()

        for line in lines:
            handled = False
            for key in keys_to_update:
                if line.strip().startswith(f"{key}="):
                    new_lines.append(f"{key}={keys_to_update[key]}\n")
                    keys_handled.add(key)
                    handled = True
                    break
            if not handled:
                new_lines.append(line)

        for key, value in keys_to_update.items():
            if key not in keys_handled:
                new_lines.append(f"{key}={value}\n")

        env_path.write_text("".join(new_lines))

        # Load it into the current process memory immediately
        os.environ["AZURE_SUBSCRIPTION_ID"] = sub_id
        if tenant_id:
            os.environ["AZURE_TENANT_ID"] = tenant_id
        if client_id:
            os.environ["AZURE_CLIENT_ID"] = client_id
        if client_secret:
            os.environ["AZURE_CLIENT_SECRET"] = client_secret

        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
