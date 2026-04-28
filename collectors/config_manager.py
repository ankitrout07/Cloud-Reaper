import os

def save_config(sub_id, tenant_id=None):
    # Write to a .env file locally
    try:
        # Check if file exists, if not create it
        if not os.path.exists(".env"):
            with open(".env", "w") as f:
                f.write("# Cloud-Reaper Configuration\n")
        
        with open(".env", "a") as f:
            f.write(f"\nAZURE_SUBSCRIPTION_ID={sub_id}")
            if tenant_id:
                f.write(f"\nAZURE_TENANT_ID={tenant_id}")
        
        # Load it into the current process memory immediately
        os.environ["AZURE_SUBSCRIPTION_ID"] = sub_id
        if tenant_id:
            os.environ["AZURE_TENANT_ID"] = tenant_id
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
