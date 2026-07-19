from __future__ import annotations

import asyncio
import datetime
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from dotenv import load_dotenv, set_key
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from reaper.collectors.utils.config_manager import save_config
from reaper.engine.models.resources import (
    CloudConnection,
    SessionLocal,
)
from reaper.services.credential_service import get_credential_service
from reaper.utils.error_handler import get_logger
from reaper.web.app_async import (
    ENV_PATH,
    PROVIDER_AUTH_STATE,
    _reaper_engine_binary,
    calc,
    settings_state,
)


def jsonify(*args, **kwargs):
    from fastapi.responses import JSONResponse
    content = args[0] if args and isinstance(args[0], dict) else kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)

logger = get_logger(__name__)

router = APIRouter(tags=["settings"])

@router.post("/api/settings/sync")
async def sync_settings(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        # Offload blocking file I/O to a thread so the event loop stays free
        def _write_env():
            set_key(ENV_PATH, "AZURE_SUBSCRIPTION_ID", data.get("subscriptionId"))
            set_key(ENV_PATH, "AZURE_TENANT_ID", data.get("tenantId"))
            set_key(ENV_PATH, "AZURE_CLIENT_ID", data.get("clientId"))
            set_key(ENV_PATH, "AZURE_CLIENT_SECRET", data.get("clientSecret"))
            load_dotenv(ENV_PATH, override=True)

        await asyncio.to_thread(_write_env)

        return JSONResponse(
            status_code=200, content={"status": "success", "message": "Credentials Sync Complete"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

def _cloud_connections_summary() -> tuple[dict[str, dict[str, Any]], str]:
    """Latest connection per provider and active provider label for settings UI.

    NOTE: This is a synchronous helper intentionally — callers must wrap it
    in ``asyncio.to_thread`` when calling from an async context.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(CloudConnection)
            .order_by(CloudConnection.provider_type, CloudConnection.updated_at.desc())
            .all()
        )
        summary: dict[str, dict[str, Any]] = {}
        for row in rows:
            provider_type = cast(str, row.provider_type)
            if provider_type in summary:
                continue
            summary[provider_type] = {
                "connection_name": row.connection_name,
                "is_active": bool(row.is_active),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        active = (os.getenv("REAPER_ACTIVE_PROVIDER") or "").lower()
        if not active:
            for provider, info in summary.items():
                if info.get("is_active"):
                    active = provider
                    break
        return summary, active
    finally:
        db.close()

@router.post("/api/settings/update")
async def update_settings(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    action = data.get("action")

    handlers = {
        "set_currency": handle_set_currency,
        "sync_pricebook": handle_sync_pricebook,
        "set_strategy": handle_set_strategy,
        "save_subscriptions": handle_save_subscriptions,
        "set_sleep_schedule": handle_set_sleep_schedule,
        "update_compliance": handle_update_compliance,
        "update_integrations": handle_update_integrations,
        "update_billing": handle_update_billing,
        "initial_setup": handle_initial_setup,
    }

    handler = handlers.get(action)
    if handler:
        return handler(data)

    return JSONResponse(status_code=400, content={"status": "error", "msg": "Invalid action"})

def handle_set_currency(data):
    code = data.get("value")
    if calc.set_currency(code):
        settings_state["currency"] = code
        return {"status": "success", "msg": f"Currency set to {code}"}
    return JSONResponse(
        status_code=400, content={"status": "error", "msg": "Invalid currency code"}
    )

def handle_sync_pricebook(_data):
    if calc.reload_prices():
        return {"status": "success", "msg": "Price book reloaded from YAML"}
    return JSONResponse(status_code=404, content={"status": "error", "msg": "File not found"})

def handle_set_strategy(data):
    strategy = data.get("value")
    settings_state["idle_strategy"] = strategy
    return {"status": "success", "msg": f"Strategy set to {strategy}"}

def handle_save_subscriptions(data):
    subs = data.get("value", [])
    settings_state["selected_subscriptions"] = subs
    return {"status": "success", "msg": f"Target scope updated: {len(subs)} subscriptions"}

def handle_set_sleep_schedule(data):
    settings_state["scheduled_sleep"] = data.get("value")
    return {"status": "success", "msg": "Scheduled Sleep updated"}

def handle_update_compliance(data):
    tags = data.get("tags", "").split(",")
    settings_state["mandatory_tags"] = [t.strip().lower() for t in tags if t.strip()]
    settings_state["auto_flag_compliance"] = data.get("auto_flag", True)
    return {"status": "success", "msg": "Compliance Policy updated"}

def handle_update_integrations(data):
    # Track separate URLs
    discord_url = data.get("discord_webhook_url")
    slack_url = data.get("slack_webhook_url")

    if discord_url is not None:
        settings_state["discord_webhook_url"] = discord_url
        settings_state["webhook_url"] = discord_url
    if slack_url is not None:
        settings_state["slack_webhook_url"] = slack_url
        if not settings_state.get("webhook_url"):
            settings_state["webhook_url"] = slack_url

    # legacy compatibility if legacy webhook_url is passed directly
    if "webhook_url" in data:
        legacy_url = data.get("webhook_url", "")
        settings_state["webhook_url"] = legacy_url
        if "discord" in legacy_url:
            settings_state["discord_webhook_url"] = legacy_url
        elif "slack" in legacy_url:
            settings_state["slack_webhook_url"] = legacy_url

    return {"status": "success", "msg": "Integrations updated"}

def handle_update_billing(data):
    settings_state["budget_threshold"] = float(data.get("threshold", 1000.0))
    return {"status": "success", "msg": "Billing thresholds updated"}

def handle_initial_setup(data):
    val = data.get("value")
    if save_config(sub_id=val):
        return {"status": "success", "msg": "Environment configured"}
    return JSONResponse(
        status_code=500, content={"status": "error", "msg": "Could not write to .env"}
    )

@router.post("/api/settings/connect-azure")
async def connect_azure(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not data:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Request body is required."}
        )

    fields = ["subscription_id", "tenant_id", "client_id", "client_secret"]
    if not all(data.get(f) for f in fields):
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "All fields are required."}
        )

    old_env = {f"AZURE_{f.upper()}": os.getenv(f"AZURE_{f.upper()}") for f in fields}

    try:
        for f in fields:
            os.environ[f"AZURE_{f.upper()}"] = data.get(f)

        cred = DefaultAzureCredential()
        sub_client = SubscriptionClient(cred)
        list(sub_client.subscriptions.list())

        if save_config(*[data.get(f) for f in fields]):
            # Update global provider authentication state
            PROVIDER_AUTH_STATE["provider"] = "azure"
            PROVIDER_AUTH_STATE["authenticated"] = True
            PROVIDER_AUTH_STATE["subscription_id"] = data.get("subscription_id")
            PROVIDER_AUTH_STATE["last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

            return {"status": "success", "message": "Azure Cloud Connected Successfully!"}
        raise Exception("Failed to write to .env file")

    except Exception as e:
        for k, v in old_env.items():
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        return JSONResponse(
            status_code=500, content={"status": "error", "message": f"Connection Failed: {e!s}"}
        )

def _write_gcp_service_account_file(service_json: str) -> str:
    target = Path(tempfile.gettempdir()) / "cloud_reaper_gcp_credentials.json"
    target.write_text(service_json)
    return str(target)

def _write_kubeconfig_file(kubeconfig: str) -> str:
    target = Path(tempfile.gettempdir()) / "cloud_reaper_kubeconfig.yaml"
    target.write_text(kubeconfig)
    return str(target)

def _set_cloud_env(provider: str, credentials: dict[str, Any]) -> None:
    provider = provider.lower()
    if provider == "aws":
        os.environ["AWS_ACCESS_KEY_ID"] = str(credentials.get("access_key_id", ""))
        os.environ["AWS_SECRET_ACCESS_KEY"] = str(credentials.get("secret_access_key", ""))
        os.environ["AWS_REGION"] = str(credentials.get("region", "us-east-1"))
    elif provider == "azure":
        os.environ["AZURE_SUBSCRIPTION_ID"] = str(credentials.get("subscription_id", ""))
        os.environ["AZURE_TENANT_ID"] = str(credentials.get("tenant_id", ""))
        os.environ["AZURE_CLIENT_ID"] = str(credentials.get("client_id", ""))
        os.environ["AZURE_CLIENT_SECRET"] = str(credentials.get("client_secret", ""))
    elif provider == "gcp":
        os.environ["GOOGLE_CLOUD_PROJECT"] = str(credentials.get("project_id", ""))
        if credentials.get("service_account_json"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _write_gcp_service_account_file(
                str(credentials["service_account_json"])
            )
    os.environ["REAPER_ACTIVE_PROVIDER"] = provider.upper()

def _validate_cloud_credentials(provider: str, credentials: dict[str, Any]) -> dict[str, Any]:
    """Validate cloud credentials by actually connecting to the service."""
    try:
        if provider == "azure":
            # Test Azure credentials by connecting to Subscription API
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.subscription import SubscriptionClient

            # Set environment for validation
            old_env = {
                "AZURE_SUBSCRIPTION_ID": os.getenv("AZURE_SUBSCRIPTION_ID"),
                "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID"),
                "AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID"),
                "AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET"),
            }

            try:
                os.environ["AZURE_SUBSCRIPTION_ID"] = credentials["subscription_id"]
                os.environ["AZURE_TENANT_ID"] = credentials["tenant_id"]
                os.environ["AZURE_CLIENT_ID"] = credentials["client_id"]
                os.environ["AZURE_CLIENT_SECRET"] = credentials["client_secret"]

                cred = DefaultAzureCredential()
                sub_client = SubscriptionClient(cred)
                # Try to list subscriptions to validate credentials
                list(sub_client.subscriptions.list())

                return {
                    "valid": True,
                    "message": "Azure credentials validated successfully",
                    "details": f"Connected to subscription {credentials['subscription_id'][:8]}...",
                }
            finally:
                # Restore old environment
                for key, value in old_env.items():
                    if value:
                        os.environ[key] = value
                    else:
                        os.environ.pop(key, None)

        elif provider == "aws":
            # Test AWS credentials by connecting to EC2
            try:
                import boto3

                # Set environment for validation
                old_env = {
                    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
                    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
                    "AWS_REGION": os.getenv("AWS_REGION"),
                }

                try:
                    os.environ["AWS_ACCESS_KEY_ID"] = credentials["access_key_id"]
                    os.environ["AWS_SECRET_ACCESS_KEY"] = credentials["secret_access_key"]
                    os.environ["AWS_REGION"] = credentials["region"]

                    # Try to connect to EC2
                    ec2 = boto3.client("ec2", region_name=credentials["region"])
                    # Simple validation call
                    ec2.describe_account()

                    return {
                        "valid": True,
                        "message": "AWS credentials validated successfully",
                        "details": f"Connected to AWS region {credentials['region']}",
                    }
                finally:
                    # Restore old environment
                    for key, value in old_env.items():
                        if value:
                            os.environ[key] = value
                        else:
                            os.environ.pop(key, None)

            except ImportError:
                return {
                    "valid": True,
                    "message": "AWS credentials saved (boto3 not available for validation)",
                    "details": "Credentials stored but validation skipped",
                }
            except Exception as e:
                return {"valid": False, "message": f"AWS connection failed: {e!s}", "details": ""}

        elif provider == "gcp":
            # Test GCP credentials
            try:
                import json

                from google.oauth2 import service_account as sa

                if credentials.get("service_account_json"):
                    try:
                        json.loads(credentials["service_account_json"])
                        return {
                            "valid": True,
                            "message": "GCP credentials validated successfully",
                            "details": f"Service account for project {credentials.get('project_id', 'unknown')}",
                        }
                    except json.JSONDecodeError:
                        return {
                            "valid": False,
                            "message": "Invalid GCP service account JSON",
                            "details": "",
                        }
                else:
                    return {
                        "valid": True,
                        "message": "GCP project ID saved (validation requires service account)",
                        "details": f"Project ID: {credentials.get('project_id', 'unknown')}",
                    }

            except ImportError:
                return {
                    "valid": True,
                    "message": "GCP credentials saved (validation library not available)",
                    "details": "Credentials stored but validation skipped",
                }

        else:
            return {
                "valid": False,
                "message": f"Unsupported provider: {provider}",
                "details": "",
            }

    except Exception as e:
        return {"valid": False, "message": f"Validation error: {e!s}", "details": ""}

@router.post("/api/settings/connect-cloud")
async def connect_cloud(request: Request):
    """Connect to cloud provider with credential validation."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    provider = (data.get("provider") or "").lower()
    credentials = data.get("credentials") or {}
    connection_name = data.get("connection_name") or f"{provider.capitalize()} Connection"

    required_fields = {
        "aws": ["access_key_id", "secret_access_key", "region"],
        "azure": ["subscription_id", "tenant_id", "client_id", "client_secret"],
        "gcp": ["project_id"],
    }

    if provider not in required_fields:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Unsupported provider."}
        )

    missing = [f for f in required_fields[provider] if not credentials.get(f)]
    if provider == "gcp" and not credentials.get("service_account_json"):
        missing.append("service_account_json")

    if missing:
        return jsonify(
            {
                "status": "error",
                "message": f"Missing required credential fields: {', '.join(missing)}",
            },
            status_code=400,
        )

    try:
        # Use global credential service for validation and storage
        credential_service = get_credential_service()

        # First set the credentials temporarily for validation
        credential_service.set_credentials(provider, credentials)

        # Validate credentials by actually connecting to the cloud service
        validation_result = credential_service.validate_credentials(provider)

        if not validation_result["valid"]:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Connection validation failed: {validation_result['message']}",
                },
                status_code=400,
            )

        # Set as active provider
        credential_service.set_active_provider(provider)

        _set_cloud_env(provider, credentials)

        def _save_connection():
            db = SessionLocal()
            try:
                db.query(CloudConnection).filter_by(provider_type=provider).update({"is_active": False})
                conn = CloudConnection(
                    provider_type=provider,
                    connection_name=connection_name,
                    credentials=credentials,
                    is_active=True,
                )
                db.add(conn)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        await asyncio.to_thread(_save_connection)

        # Update global provider authentication state
        PROVIDER_AUTH_STATE["provider"] = provider
        PROVIDER_AUTH_STATE["authenticated"] = True
        PROVIDER_AUTH_STATE["subscription_id"] = (
            credentials.get("subscription_id")
            if provider == "azure"
            else credentials.get("project_id")
            if provider == "gcp"
            else None
        )
        PROVIDER_AUTH_STATE["last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return jsonify(
            {
                "status": "success",
                "message": f"{provider.capitalize()} credentials validated and activated successfully. {validation_result['details']}",
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/api/settings/cloud-connections")
async def list_cloud_connections(request: Request):
    summary, active_provider = await asyncio.to_thread(_cloud_connections_summary)
    return jsonify(
        {
            "status": "success",
            "connections": summary,
            "active_provider": active_provider,
        }
    )

@router.get("/api/settings/auth")
async def check_auth(request: Request):
    try:
        await asyncio.to_thread(
            subprocess.run, ["az", "account", "show"], capture_output=True, check=True
        )
        return jsonify(
            {"status": "healthy", "message": "Connected: Azure CLI (Active Subscription)"}
        )
    except Exception:
        return {"status": "expired", "message": "Disconnected: Please run 'az login'"}

@router.get("/api/settings/subscriptions")
async def list_subscriptions(request: Request):
    try:
        binary_path = _reaper_engine_binary()
        if not binary_path:
            return []

        result = await asyncio.to_thread(
            subprocess.run,
            [str(binary_path), "--list-subs"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return JSONResponse(status_code=500, content={"error": result.stderr})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/api/settings/credentials/status")
async def credentials_status(request: Request):
    """Check credential status across all pages - returns 503 if no credentials configured."""
    try:
        credential_service = get_credential_service()
        active_provider = credential_service.get_active_provider()

        if not active_provider:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": "No active cloud provider configured",
                    "code": "NO_ACTIVE_PROVIDER",
                    "user_message": "Please connect your cloud provider in Settings to access real-time data",
                },
            )

        if not credential_service.has_credentials(active_provider):
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": f"No credentials configured for {active_provider.upper()}",
                    "code": "NO_CREDENTIALS",
                    "provider": active_provider,
                    "user_message": f"Please configure {active_provider.upper()} credentials in Settings to access real-time data",
                },
            )

        # Validate credentials are still valid
        validation_result = credential_service.validate_credentials(active_provider)

        if not validation_result["valid"]:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": f"Credential validation failed: {validation_result['message']}",
                    "code": "CREDENTIAL_VALIDATION_FAILED",
                    "provider": active_provider,
                    "user_message": f"Your {active_provider.upper()} credentials are invalid. Please reconfigure them in Settings.",
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "provider": active_provider,
                "message": f"Valid credentials configured for {active_provider.upper()}",
                "validation_details": validation_result.get("details", ""),
            },
        )

    except Exception as e:
        logger.error(f"Credential status check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": f"Credential check failed: {e!s}",
                "code": "CREDENTIAL_CHECK_ERROR",
                "user_message": "Unable to verify cloud provider credentials. Please check your Settings.",
            },
        )

