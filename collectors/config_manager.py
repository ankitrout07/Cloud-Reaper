import os

def save_config(sub_id, tenant_id=None):
    # Write to a .env file locally
    try:
        env_path = ".env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
        
        # Prepare new content
        new_lines = []
        keys_to_update = {"AZURE_SUBSCRIPTION_ID": sub_id}
        if tenant_id:
            keys_to_update["AZURE_TENANT_ID"] = tenant_id
            
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
        
        # Add keys that weren't in the file
        for key in keys_to_update:
            if key not in keys_handled:
                new_lines.append(f"{key}={keys_to_update[key]}\n")
                
        with open(env_path, "w") as f:
            f.writelines(new_lines)
        
        # Load it into the current process memory immediately
        os.environ["AZURE_SUBSCRIPTION_ID"] = sub_id
        if tenant_id:
            os.environ["AZURE_TENANT_ID"] = tenant_id
            
        # Also try to clear the AzureCollector cache if any
        # (This is handled by fresh instance creation in app.py routes)
        
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
