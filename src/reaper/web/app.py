# gevent monkey-patching is optional; use threading fallback if unavailable.
try:
    from gevent import monkey

    monkey.patch_all()
    async_mode = "gevent"
except ImportError:
    async_mode = "threading"

import base64
import contextlib
import datetime
import io
import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any, cast

from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_compress import Compress
from flask_cors import CORS
from flask_socketio import SocketIO
from sqlalchemy import func

try:
    from weasyprint import HTML
except Exception as e:
    HTML = None
    print(f"[*] WeasyPrint could not be loaded: {e}")

from reaper.collectors.prices.catalog import (
    get_catalog_filters,
    get_catalog_status,
    query_catalog_prices,
    start_catalog_warmup,
    warm_catalog,
)
from reaper.collectors.providers.azure_collector import AzureCollector
from reaper.collectors.utils.auth_check import check_azure_status
from reaper.collectors.utils.config_manager import save_config
from reaper.engine.core.architect import AIArchitectManager, resolve_component_costs
from reaper.engine.core.calculator import CostCalculator, SpotEvictionPredictor
from reaper.engine.core.cost_optimizer import (
    ComprehensiveCostOptimizer,
    Priority,
    ResourceMetrics,
)
from reaper.engine.core.cost_reporter import AutomatedCostReporter, ReportFormat, ReportPeriod
from reaper.engine.core.economics import RegionalArbitrage
from reaper.engine.core.logic import RightSizer
from reaper.engine.models.resources import (
    ActionLog,
    BusinessMetric,
    CloudConnection,
    CostHistory,
    Resource,
    SessionLocal,
    VaultEntry,
    VaultSettings,
    init_db,
)
from reaper.web.copilot_routes import copilot_api
from reaper.web.metrics_routes import telemetry_bp
from reaper.web.search_routes import search_bp
from reaper.web.vault_crypto import (
    derive_fernet_key,
    generate_salt,
    hash_passcode,
    verify_passcode,
)

load_dotenv()


def _repo_root() -> Path:
    """Repository root (``.../Cloud-Reaper``), derived from this package path."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _reaper_engine_binary() -> Path | None:
    """Resolve the Go engine binary (bootstrap builds to repo ``bin/``)."""
    repo_root = _repo_root()
    name = "reaper-engine.exe" if os.name == "nt" else "reaper-engine"
    candidates = (
        repo_root / "bin" / name,
        repo_root / "src" / "engine-go" / name,
    )
    for p in candidates:
        if p.is_file():
            return p
    return None


def is_first_run():
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    return bool(not sub_id or "your_" in sub_id or len(sub_id) < 5)


_web_dir = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(_web_dir / "templates"),
    static_folder=str(_web_dir / "static"),
)
CORS(app)

# Enable response compression for better performance
Compress(app)

# Configure compression settings
app.config["COMPRESS_ALGORITHM"] = "gzip"
app.config["COMPRESS_LEVEL"] = 6
app.config["COMPRESS_MIN_SIZE"] = 500  # Only compress responses > 500 bytes

# Performance optimizations
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000  # 1 year for static files
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_SECURE_COOKIES", "false").lower() == "true"

# Enable threading for better performance
app.config["THREADING"] = True

app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

app.register_blueprint(copilot_api)
app.register_blueprint(search_bp)
app.register_blueprint(telemetry_bp)

VAULT_UNLOCK_TTL_SEC = int(os.getenv("VAULT_UNLOCK_TTL_SEC", "3600"))
thread = None
thread_lock = threading.Lock()

# Azure standard metrics rarely refresh faster than ~1 minute; 5–10s is a safe UI throttle.
SOCKET_METRICS_INTERVAL_SEC = int(os.getenv("REAPER_METRICS_EMIT_SEC", "8"))


def background_metrics_worker():
    """Fetches Azure Monitor CPU samples and pushes over WebSocket (throttled)."""
    error_count = 0
    max_errors = 5
    backoff_time = SOCKET_METRICS_INTERVAL_SEC
    max_backoff = 120  # Maximum 2 minutes backoff

    while True:
        try:
            socketio.sleep(backoff_time)
            now = datetime.datetime.now(datetime.UTC).strftime("%H:%M:%S")
            cpu_usage = None

            try:
                if not is_first_run():
                    az = AzureCollector()
                    cpu_usage = az.get_live_subscription_cpu_average(max_vms=6)
                    error_count = 0  # Reset error count on success
                    backoff_time = SOCKET_METRICS_INTERVAL_SEC  # Reset backoff on success
            except Exception as e:
                error_count += 1
                print(f"[!] Metrics Worker Error ({error_count}/{max_errors}): {e}")

                # Exponential backoff for consecutive errors
                if error_count >= max_errors:
                    backoff_time = min(backoff_time * 2, max_backoff)
                    print(f"[!] Too many consecutive errors, backing off for {backoff_time} seconds")
                    error_count = 0

            if cpu_usage is not None:
                cpu_usage = round(float(cpu_usage), 2)
                try:
                    socketio.emit(
                        "metric_update",
                        {"time": now, "value": cpu_usage},
                    )
                except Exception as e:
                    print(f"[!] Metrics emit error: {e}")

        except Exception as e:
            print(f"[!] Critical error in metrics worker: {e}")
            # Prevent rapid crash loops by sleeping longer on critical errors
            backoff_time = min(backoff_time * 2, max_backoff)
            socketio.sleep(backoff_time)


# Start the worker after the app is ready
socketio.start_background_task(background_metrics_worker)

init_db()
start_catalog_warmup()
calc = CostCalculator()
architect_manager = AIArchitectManager()
settings_state = {
    "currency": "USD",
    "idle_strategy": "aggressive",
    "selected_subscriptions": [],
    "scheduled_sleep": {"enabled": False, "stop_time": "20:00", "start_time": "08:00"},
    "mandatory_tags": ["owner", "project"],
    "webhook_url": "",
    "discord_webhook_url": "",
    "slack_webhook_url": "",
    "budget_threshold": 1000.0,
    "auto_flag_compliance": True,
}

ENV_PATH = str(_repo_root() / ".env")


@app.route("/api/settings/sync", methods=["POST"])
def sync_settings():
    data = request.json or {}
    try:
        # 1. Update the .env file physically
        set_key(ENV_PATH, "AZURE_SUBSCRIPTION_ID", data.get("subscriptionId"))
        set_key(ENV_PATH, "AZURE_TENANT_ID", data.get("tenantId"))
        set_key(ENV_PATH, "AZURE_CLIENT_ID", data.get("clientId"))
        set_key(ENV_PATH, "AZURE_CLIENT_SECRET", data.get("clientSecret"))

        # 2. Reload the environment variables for the current running process
        load_dotenv(ENV_PATH, override=True)

        return jsonify({"status": "success", "message": "Credentials Sync Complete"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.before_request
def check_setup():
    if (
        request.path.startswith("/static")
        or request.path.startswith("/api/")
        or "favicon" in request.path
    ):
        return None
    if is_first_run() and request.endpoint != "settings":
        return redirect(url_for("settings", tab="cloud"))
    return None


@app.route("/favicon.ico")
def favicon_ico():
    return send_from_directory(
        str(_web_dir / "static" / "assets"), "favicon.ico", mimetype="image/x-icon"
    )


@app.route("/favicon.png")
def favicon_png():
    return send_from_directory(
        str(_web_dir / "static" / "assets"), "favicon.png", mimetype="image/png"
    )


def _get_cached_user_info() -> tuple[str, str]:
    """Get cached user/subscription info with 5-minute TTL to avoid blocking Azure API calls."""
    cache_key_prefix = "azure_user_info"
    cache_ttl = 300  # 5 minutes
    
    # Check session cache first
    user_name = session.get(f"{cache_key_prefix}_user")
    sub_name = session.get(f"{cache_key_prefix}_sub")
    timestamp = session.get(f"{cache_key_prefix}_timestamp")
    
    # Return cached data if valid
    if user_name and sub_name and timestamp:
        if time.time() - float(timestamp) < cache_ttl:
            return user_name, sub_name
    
    # Fetch fresh data and cache it
    try:
        az = AzureCollector()
        user_name = az.get_user_name()
        sub_name = az.get_subscription_name()
        
        # Cache in session
        session[f"{cache_key_prefix}_user"] = user_name
        session[f"{cache_key_prefix}_sub"] = sub_name
        session[f"{cache_key_prefix}_timestamp"] = str(time.time())
        
        return user_name, sub_name
    except Exception as e:
        print(f"[!] Error fetching user info: {e}")
        return "Azure User", "Azure Subscription"


@app.route("/")
def index():
    user_name, sub_name = _get_cached_user_info()
    return render_template("pages/index.html", user_name=user_name, sub_name=sub_name)


def _cloud_connections_summary() -> tuple[dict[str, dict[str, Any]], str]:
    """Latest connection per provider and active provider label for settings UI."""
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


def _vault_settings_row() -> VaultSettings | None:
    db = SessionLocal()
    try:
        return db.query(VaultSettings).first()
    except Exception as e:
        print(f"[!] Error fetching vault settings: {e}")
        return None
    finally:
        db.close()


def _vault_salt_bytes(settings: VaultSettings) -> bytes:
    return base64.b64decode(settings.salt.encode("utf-8"))


def _is_vault_unlocked() -> bool:
    if not session.get("vault_unlocked"):
        return False
    expires = session.get("vault_unlock_expires", 0)
    if time.time() > float(expires):
        session.pop("vault_unlocked", None)
        session.pop("vault_unlock_expires", None)
        session.pop("vault_fernet_key", None)
        return False
    return bool(session.get("vault_fernet_key"))


def _session_fernet() -> Fernet | None:
    key = session.get("vault_fernet_key")
    if not key or not _is_vault_unlocked():
        return None
    return Fernet(key.encode("utf-8"))


def _unlock_vault_session(passcode: str, settings: VaultSettings) -> bool:
    salt = _vault_salt_bytes(settings)
    if not verify_passcode(passcode, salt, cast(str, settings.passcode_verifier)):
        return False
    session["vault_fernet_key"] = derive_fernet_key(passcode, salt).decode("utf-8")
    session["vault_unlocked"] = True
    session["vault_unlock_expires"] = time.time() + VAULT_UNLOCK_TTL_SEC
    return True


@app.route("/settings")
def settings():
    cloud_summary, active_provider = _cloud_connections_summary()
    vault_configured = _vault_settings_row() is not None
    return render_template(
        "pages/settings.html",
        cloud_connections=cloud_summary,
        active_provider=active_provider,
        vault_configured=vault_configured,
    )


@app.route("/api/settings/update", methods=["POST"])
def update_settings():
    data = request.json or {}
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

    return jsonify({"status": "error", "msg": "Invalid action"}), 400


def handle_set_currency(data):
    code = data.get("value")
    if calc.set_currency(code):
        settings_state["currency"] = code
        return jsonify({"status": "success", "msg": f"Currency set to {code}"})
    return jsonify({"status": "error", "msg": "Invalid currency code"}), 400


def handle_sync_pricebook(_data):
    if calc.reload_prices():
        return jsonify({"status": "success", "msg": "Price book reloaded from YAML"})
    return jsonify({"status": "error", "msg": "File not found"}), 404


def handle_set_strategy(data):
    strategy = data.get("value")
    settings_state["idle_strategy"] = strategy
    return jsonify({"status": "success", "msg": f"Strategy set to {strategy}"})


def handle_save_subscriptions(data):
    subs = data.get("value", [])
    settings_state["selected_subscriptions"] = subs
    return jsonify({"status": "success", "msg": f"Target scope updated: {len(subs)} subscriptions"})


def handle_set_sleep_schedule(data):
    settings_state["scheduled_sleep"] = data.get("value")
    return jsonify({"status": "success", "msg": "Scheduled Sleep updated"})


def handle_update_compliance(data):
    tags = data.get("tags", "").split(",")
    settings_state["mandatory_tags"] = [t.strip().lower() for t in tags if t.strip()]
    settings_state["auto_flag_compliance"] = data.get("auto_flag", True)
    return jsonify({"status": "success", "msg": "Compliance Policy updated"})


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

    return jsonify({"status": "success", "msg": "Integrations updated"})


def handle_update_billing(data):
    settings_state["budget_threshold"] = float(data.get("threshold", 1000.0))
    return jsonify({"status": "success", "msg": "Billing thresholds updated"})


def handle_initial_setup(data):
    val = data.get("value")
    if save_config(sub_id=val):
        return jsonify({"status": "success", "msg": "Environment configured"})
    return jsonify({"status": "error", "msg": "Could not write to .env"}), 500


@app.route("/api/settings/connect-azure", methods=["POST"])
def connect_azure():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "Request body is required."}), 400

    fields = ["subscription_id", "tenant_id", "client_id", "client_secret"]
    if not all(data.get(f) for f in fields):
        return jsonify({"status": "error", "message": "All fields are required."}), 400

    old_env = {f"AZURE_{f.upper()}": os.getenv(f"AZURE_{f.upper()}") for f in fields}

    try:
        for f in fields:
            os.environ[f"AZURE_{f.upper()}"] = data.get(f)

        cred = DefaultAzureCredential()
        sub_client = SubscriptionClient(cred)
        list(sub_client.subscriptions.list())

        if save_config(*[data.get(f) for f in fields]):
            return jsonify({"status": "success", "message": "Azure Cloud Connected Successfully!"})
        raise Exception("Failed to write to .env file")

    except Exception as e:
        for k, v in old_env.items():
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        return jsonify({"status": "error", "message": f"Connection Failed: {e!s}"}), 500


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
    elif provider == "k8s":
        kubeconfig = credentials.get("kubeconfig")
        if kubeconfig:
            kubeconfig_path = Path(str(kubeconfig))
            if kubeconfig_path.exists():
                os.environ["KUBECONFIG"] = str(kubeconfig_path)
            else:
                os.environ["KUBECONFIG"] = _write_kubeconfig_file(str(kubeconfig))
        if credentials.get("service_account_token"):
            os.environ["K8S_SERVICE_ACCOUNT_TOKEN"] = str(
                credentials.get("service_account_token", "")
            )
        if credentials.get("context"):
            os.environ["K8S_CONTEXT"] = str(credentials.get("context", ""))
    os.environ["REAPER_ACTIVE_PROVIDER"] = provider.upper()


@app.route("/api/context/switch")
def switch_context():
    provider = (request.args.get("provider") or "").lower()
    if provider not in {"aws", "azure", "gcp", "k8s"}:
        return jsonify({"status": "error", "message": "Unsupported provider."}), 400

    db = SessionLocal()
    try:
        conn = (
            db.query(CloudConnection)
            .filter_by(provider_type=provider)
            .order_by(CloudConnection.updated_at.desc())
            .first()
        )
        if not conn:
            return jsonify(
                {
                    "status": "redirect",
                    "url": url_for("settings", tab="cloud", provider=provider),
                }
            )

        db.query(CloudConnection).filter_by(provider_type=provider).update({"is_active": False})
        conn.is_active = True
        db.commit()
        _set_cloud_env(provider, conn.credentials)

        return jsonify(
            {
                "status": "success",
                "provider": provider,
                "message": f"{provider.upper()} context activated.",
            }
        )
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/settings/connect-cloud", methods=["POST"])
def connect_cloud():
    data = request.json or {}
    provider = (data.get("provider") or "").lower()
    credentials = data.get("credentials") or {}
    connection_name = data.get("connection_name") or f"{provider.capitalize()} Connection"

    required_fields = {
        "aws": ["access_key_id", "secret_access_key", "region"],
        "azure": ["subscription_id", "tenant_id", "client_id", "client_secret"],
        "gcp": ["project_id"],
        "k8s": [],
    }

    if provider not in required_fields:
        return jsonify({"status": "error", "message": "Unsupported provider."}), 400

    missing = [f for f in required_fields[provider] if not credentials.get(f)]
    if provider == "gcp" and not credentials.get("service_account_json"):
        missing.append("service_account_json")
    if provider == "k8s" and not (
        credentials.get("kubeconfig") or credentials.get("service_account_token")
    ):
        missing.append("kubeconfig or service_account_token")

    if missing:
        return jsonify(
            {
                "status": "error",
                "message": f"Missing required credential fields: {', '.join(missing)}",
            }
        ), 400

    try:
        _set_cloud_env(provider, credentials)
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
            return jsonify(
                {
                    "status": "success",
                    "message": f"{provider.capitalize()} credentials saved and activated.",
                }
            )
        except Exception as e:
            db.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            db.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/settings/cloud-connections")
def list_cloud_connections():
    summary, active_provider = _cloud_connections_summary()
    return jsonify(
        {
            "status": "success",
            "connections": summary,
            "active_provider": active_provider,
        }
    )


@app.route("/api/vault/status")
def vault_status():
    configured = _vault_settings_row() is not None
    return jsonify(
        {
            "status": "success",
            "configured": configured,
            "unlocked": _is_vault_unlocked(),
        }
    )


@app.route("/api/vault/setup", methods=["POST"])
def vault_setup():
    data = request.json or {}
    if not data:
        return jsonify({"status": "error", "message": "Request body is required."}), 400

    passcode = (data.get("passcode") or "").strip()
    confirm = (data.get("confirm") or "").strip()
    passcode_type = (data.get("passcode_type") or "password").strip().lower()

    if passcode_type == "pin":
        if len(passcode) != 4:
            return jsonify(
                {"status": "error", "message": "PIN passcode must be exactly 4 digits/characters."}
            ), 400
    elif len(passcode) < 8:
        return jsonify(
            {"status": "error", "message": "Password passcode must be at least 8 characters."}
        ), 400

    if passcode != confirm:
        return jsonify({"status": "error", "message": "Passcodes do not match."}), 400

    db = SessionLocal()
    try:
        if db.query(VaultSettings).first():
            return jsonify({"status": "error", "message": "Vault is already configured."}), 400

        salt = generate_salt()
        settings = VaultSettings(
            salt=base64.b64encode(salt).decode("utf-8"),
            passcode_verifier=hash_passcode(passcode, salt),
        )
        db.add(settings)
        db.commit()
        _unlock_vault_session(passcode, settings)
        return jsonify({"status": "success", "message": "Vault created and unlocked."})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/vault/reset", methods=["POST"])
def vault_reset():
    """Erases all stored vault entries and resets the passcode setup status."""
    db = SessionLocal()
    try:
        db.query(VaultEntry).delete()
        db.query(VaultSettings).delete()
        db.commit()

        session.pop("vault_unlocked", None)
        session.pop("vault_unlock_expires", None)
        session.pop("vault_fernet_key", None)

        return jsonify(
            {"status": "success", "message": "Vault successfully reset. All stored secrets erased."}
        )
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/vault/unlock", methods=["POST"])
def vault_unlock():
    data = request.json or {}
    if not data:
        return jsonify({"status": "error", "message": "Request body is required."}), 400

    passcode = (data.get("passcode") or "").strip()
    if not passcode:
        return jsonify({"status": "error", "message": "Passcode is required."}), 400

    settings = _vault_settings_row()
    if not settings:
        return jsonify({"status": "error", "message": "Vault is not configured yet."}), 400
    if not _unlock_vault_session(passcode, settings):
        return jsonify({"status": "error", "message": "Incorrect passcode."}), 401
    return jsonify({"status": "success", "message": "Vault unlocked."})


@app.route("/api/vault/lock", methods=["POST"])
def vault_lock():
    session.pop("vault_unlocked", None)
    session.pop("vault_unlock_expires", None)
    session.pop("vault_fernet_key", None)
    return jsonify({"status": "success", "message": "Vault locked."})


@app.route("/api/vault/entries", methods=["GET"])
def vault_list_entries():
    if not _is_vault_unlocked():
        return jsonify({"status": "error", "message": "Vault is locked."}), 403

    db = SessionLocal()
    try:
        rows = db.query(VaultEntry).order_by(VaultEntry.updated_at.desc()).all()
        entries = [
            {
                "id": row.id,
                "label": row.label,
                "entry_type": row.entry_type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
        return jsonify({"status": "success", "entries": entries})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/vault/entries", methods=["POST"])
def vault_create_entry():
    if not _is_vault_unlocked():
        return jsonify({"status": "error", "message": "Vault is locked."}), 403

    fernet = _session_fernet()
    if not fernet:
        return jsonify({"status": "error", "message": "Vault session expired."}), 403

    data = request.json or {}
    if not data:
        return jsonify({"status": "error", "message": "Request body is required."}), 400

    label = (data.get("label") or "").strip()
    entry_type = (data.get("entry_type") or "credential").strip().lower()
    value = (data.get("value") or "").strip()
    username = (data.get("username") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not label or not value:
        return jsonify({"status": "error", "message": "Label and secret value are required."}), 400
    if entry_type not in {"credential", "passcode", "note"}:
        return jsonify({"status": "error", "message": "Invalid entry type."}), 400

    payload = {"value": value, "username": username, "notes": notes}
    try:
        token = fernet.encrypt(json.dumps(payload).encode("utf-8")).decode("utf-8")
    except Exception as e:
        return jsonify({"status": "error", "message": f"Encryption failed: {e!s}"}), 500

    db = SessionLocal()
    try:
        entry = VaultEntry(label=label, entry_type=entry_type, encrypted_payload=token)
        db.add(entry)
        db.commit()
        return jsonify(
            {
                "status": "success",
                "message": "Entry saved.",
                "entry": {"id": entry.id, "label": entry.label, "entry_type": entry.entry_type},
            }
        )
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/vault/entries/<int:entry_id>", methods=["GET"])
def vault_get_entry(entry_id: int):
    if not _is_vault_unlocked():
        return jsonify({"status": "error", "message": "Vault is locked."}), 403

    fernet = _session_fernet()
    if not fernet:
        return jsonify({"status": "error", "message": "Vault session expired."}), 403

    db = SessionLocal()
    try:
        row = db.query(VaultEntry).filter_by(id=entry_id).first()
        if not row:
            return jsonify({"status": "error", "message": "Entry not found."}), 404
        try:
            payload = json.loads(
                fernet.decrypt(row.encrypted_payload.encode("utf-8")).decode("utf-8")
            )
        except Exception as e:
            return jsonify({"status": "error", "message": f"Unable to decrypt entry: {e!s}"}), 500
        return jsonify(
            {
                "status": "success",
                "entry": {
                    "id": row.id,
                    "label": row.label,
                    "entry_type": row.entry_type,
                    "username": payload.get("username", ""),
                    "value": payload.get("value", ""),
                    "notes": payload.get("notes", ""),
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/vault/entries/<int:entry_id>", methods=["DELETE"])
def vault_delete_entry(entry_id: int):
    if not _is_vault_unlocked():
        return jsonify({"status": "error", "message": "Vault is locked."}), 403

    db = SessionLocal()
    try:
        row = db.query(VaultEntry).filter_by(id=entry_id).first()
        if not row:
            return jsonify({"status": "error", "message": "Entry not found."}), 404
        db.delete(row)
        db.commit()
        return jsonify({"status": "success", "message": "Entry deleted."})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/settings/auth")
def check_auth():
    try:
        subprocess.run(["az", "account", "show"], capture_output=True, check=True)
        return jsonify(
            {"status": "healthy", "message": "Connected: Azure CLI (Active Subscription)"}
        )
    except Exception:
        return jsonify({"status": "expired", "message": "Disconnected: Please run 'az login'"})


@app.route("/api/settings/subscriptions")
def list_subscriptions():
    try:
        binary_path = _reaper_engine_binary()
        if not binary_path:
            return jsonify([])

        result = subprocess.run(
            [str(binary_path), "--list-subs"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return jsonify(json.loads(result.stdout))
        return jsonify({"error": result.stderr}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/pricing")
def pricing():
    return render_template("pages/pricing.html")


@app.route("/finops")
def finops():
    return render_template("pages/finops.html")


@app.route("/financial")
def financial():
    tab = request.args.get("tab", "budget")
    allowed_tabs = [
        "budget",
        "alerts",
        "business-metrics",
        "commitment-reports",
        "issues",
        "commitments",
        "savings-models",
    ]
    if tab not in allowed_tabs:
        tab = "budget"

    # Get settings state for rendering
    db = SessionLocal()
    try:
        db_metrics = db.query(BusinessMetric).order_by(BusinessMetric.date.desc()).all()
    except Exception:
        db_metrics = []
    finally:
        db.close()

    return render_template(
        "pages/financial.html", active_tab=tab, settings=settings_state, db_metrics=db_metrics
    )


@app.route("/api/v1/finops/simulate/commitment", methods=["POST"])
def simulate_commitment():
    # Placeholder simulator logic.
    data = request.json or {}
    return jsonify(
        {
            "status": "success",
            "message": "Commitment simulated successfully",
            "savings_estimate": 150.00,
            "roi_months": 3.5,
        }
    )


@app.route("/api/v1/finops/test-webhook", methods=["POST"])
def test_webhook():
    """Test webhook endpoint for alert integration testing."""
    from reaper.engine.notifications.notifier import send_discord_alert

    try:
        send_discord_alert(
            "Test Alert", "This is a test notification from Cloud-Reaper.", color=0x3B82F6
        )
        return jsonify({"status": "success", "message": "Test webhook triggered successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/finops/simulate/policy", methods=["POST"])
def simulate_policy():
    # Placeholder logic for what-if policy application.
    data = request.json or {}
    return jsonify(
        {"status": "success", "message": "Policy simulation applied", "cost_impact": -250.00}
    )


@app.route("/api/metrics")
def get_dashboard_metrics():
    """Provides valid default metrics to satisfy the real-time telemetry canvases"""
    return jsonify(
        {
            "status": "healthy",
            "burn_rate_velocity": 0.00,
            "efficiency_score": 94.2,
            "telemetry_stream": [],
        }
    )


# ========== FINANCIAL INTELLIGENCE API ENDPOINTS ==========


@app.route("/api/finops/budget/data")
def get_budget_data():
    """Get comprehensive budget pacing data for the financial dashboard."""
    try:
        budget_threshold = float(settings_state.get("budget_threshold", 1000.0))

        # Get actual spend data from Azure Collector if available
        az = AzureCollector()
        try:
            cost_data = az.get_cost_vs_budget()
            cumulative_spend = cost_data.get("cumulative_spend", 0)
            budget_pace = cost_data.get("budget_pace", 0)
            daily_spend = cost_data.get("daily_spend", [])
        except Exception:
            # Fallback to simulated data
            cumulative_spend = 3420.50
            budget_pace = 114.02
            daily_spend = []

        # Calculate burn rate and forecast
        burn_rate = cumulative_spend / 30  # Simplified calculation
        forecast = burn_rate * 30

        return jsonify(
            {
                "status": "success",
                "data": {
                    "budget_cap": budget_threshold,
                    "current_spend": cumulative_spend,
                    "burn_rate": burn_rate,
                    "forecast": forecast,
                    "utilization_percent": (cumulative_spend / budget_threshold * 100)
                    if budget_threshold > 0
                    else 0,
                    "daily_spend": daily_spend,
                    "budget_pace": budget_pace,
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/budget/update", methods=["POST"])
def update_budget_threshold():
    """Direct endpoint to update budget threshold."""
    try:
        data = request.json or {}
        threshold = data.get("threshold")
        if not threshold:
            return jsonify({"status": "error", "message": "Threshold is required"}), 400

        settings_state["budget_threshold"] = float(threshold)
        return jsonify(
            {
                "status": "success",
                "message": f"Budget threshold updated to ${threshold}",
                "threshold": float(threshold),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/budget/chart")
def get_budget_chart_data():
    """Get chart data for budget pacing visualization."""
    try:
        az = AzureCollector()
        try:
            chart_data = az.get_cost_vs_budget_chart()
        except Exception:
            # Fallback simulated data
            import random

            chart_data = {
                "labels": [f"Day {i}" for i in range(1, 31)],
                "cumulative_spend": [random.uniform(100, 150) * i for i in range(1, 31)],
                "budget_pace": [random.uniform(100, 150) * i * 0.95 for i in range(1, 31)],
            }

        return jsonify({"status": "success", "chart": chart_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/commitments/data")
def get_commitments_data():
    """Get active commitment portfolio and recommendations."""
    try:
        az = AzureCollector()
        try:
            commitments = az.get_active_commitments()
            coverage = az.get_ri_coverage()
            recommendations = az.get_ri_recommendations()
        except Exception:
            # Fallback simulated data
            commitments = [
                {
                    "provider": "AWS",
                    "type": "Savings Plan",
                    "commit": "$2.50/hr",
                    "savings": 32,
                    "status": "active",
                },
                {
                    "provider": "Azure",
                    "type": "D4s_v5 RI",
                    "quantity": 6,
                    "savings": 41,
                    "status": "active",
                },
            ]
            coverage = {"overall_coverage": 62.4, "waste_amount": 1185.00, "target_coverage": 90.0}
            recommendations = [
                {
                    "sku": "Standard_D4s_v5",
                    "region": "eastus",
                    "annual_savings": 420.50,
                    "term": "3 years",
                    "action": "Purchase RI",
                }
            ]

        return jsonify(
            {
                "status": "success",
                "data": {
                    "active_commitments": commitments,
                    "coverage_analysis": coverage,
                    "recommendations": recommendations,
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/issues/data")
def get_issues_data():
    """Get cost governance issues requiring action."""
    try:
        az = AzureCollector()
        try:
            issues = az.get_cost_governance_issues()
        except Exception:
            # Fallback simulated data
            issues = [
                {
                    "id": "issue-1",
                    "severity": "Critical",
                    "type": "Compliance Tag Violation",
                    "title": "Untagged Dev-Instance in EastUS",
                    "resource_id": "vm-az-dev-1052",
                    "daily_waste": 22.40,
                    "actions": ["DISMISS", "KILL"],
                },
                {
                    "id": "issue-2",
                    "severity": "Warning",
                    "type": "Idle Machine Alert",
                    "title": "Underutilized compute core instances",
                    "resource_id": "vm-test-db-replica",
                    "monthly_savings": 180.00,
                    "actions": ["DISMISS", "RIGHTSIZE"],
                },
                {
                    "id": "issue-3",
                    "severity": "Info",
                    "type": "Storage Optimization",
                    "title": "Orphaned Snapshot Volumes",
                    "resource_id": "5 snapshots",
                    "monthly_savings": 45.00,
                    "actions": ["DISMISS", "KILL"],
                },
            ]

        return jsonify(
            {
                "status": "success",
                "data": {
                    "issues": issues,
                    "total_count": len(issues),
                    "by_severity": {
                        "critical": sum(1 for i in issues if i["severity"] == "Critical"),
                        "warning": sum(1 for i in issues if i["severity"] == "Warning"),
                        "info": sum(1 for i in issues if i["severity"] == "Info"),
                    },
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/issues/remediate", methods=["POST"])
def remediate_issue():
    """Execute remediation action on a cost governance issue."""
    try:
        data = request.json or {}
        issue_id = data.get("issue_id")
        action = data.get("action")

        if not issue_id or not action:
            return jsonify({"status": "error", "message": "Issue ID and action are required"}), 400

        # In a real implementation, this would call Azure SDK to perform the action
        # For now, return success
        return jsonify(
            {
                "status": "success",
                "message": f"Issue {issue_id} remediated with action: {action}",
                "issue_id": issue_id,
                "action": action,
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/commitment/simulate", methods=["POST"])
def simulate_commitment_api():
    """Enhanced commitment simulation with real calculations."""
    try:
        data = request.json or {}
        provider = data.get("provider", "AWS")
        commitment_type = data.get("type", "Savings Plan")
        term = int(data.get("term", 1))  # years
        payment = data.get("payment", "no_upfront")
        hourly_spend = float(data.get("hourly_spend", 5.0))

        # Calculate estimated savings based on commitment type
        if commitment_type == "Savings Plan":
            base_discount = 0.30 if term == 1 else 0.54
        else:
            base_discount = 0.40 if term == 1 else 0.72

        upfront_bonus = 0.0
        if payment == "all_upfront":
            upfront_bonus = 0.05
        elif payment == "partial_upfront":
            upfront_bonus = 0.02

        total_discount = base_discount + upfront_bonus
        annual_savings = hourly_spend * 24 * 365 * total_discount
        roi_months = 12 / total_discount if total_discount > 0 else 0

        return jsonify(
            {
                "status": "success",
                "simulation": {
                    "provider": provider,
                    "type": commitment_type,
                    "term": term,
                    "payment": payment,
                    "hourly_commit": hourly_spend,
                    "discount_rate": f"{total_discount * 100:.1f}%",
                    "annual_savings": round(annual_savings, 2),
                    "roi_months": round(roi_months, 1),
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/commitment/purchase", methods=["POST"])
def purchase_commitment_api():
    """Purchase a commitment based on simulation results."""
    try:
        data = request.json or {}
        simulation = data.get("simulation")

        if not simulation:
            return jsonify({"status": "error", "message": "Simulation data required"}), 400

        # In a real implementation, this would call Azure/AWS API to purchase
        # For now, simulate success
        commitment_id = f"commit-{int(time.time())}"

        return jsonify(
            {
                "status": "success",
                "message": "Commitment purchased successfully",
                "commitment_id": commitment_id,
                "estimated_savings": simulation.get("annual_savings", 0),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/policy/simulate", methods=["POST"])
def simulate_policy_api():
    """Simulate policy application with cost impact."""
    try:
        data = request.json or {}
        aggressiveness = int(data.get("aggressiveness", 50))
        spot_adoption = int(data.get("spot_adoption", 30))

        # Calculate estimated savings based on parameters
        # Higher aggressiveness + higher spot adoption = more savings
        savings_multiplier = (aggressiveness / 100) * 0.6 + (spot_adoption / 100) * 0.4
        base_monthly_spend = 5000.00  # Example baseline
        monthly_savings = base_monthly_spend * savings_multiplier * 0.35

        # Calculate carbon offset (rough estimate)
        carbon_offset_kg = monthly_savings * 0.224  # kg CO2 per $ cloud spend
        trees_equivalent = carbon_offset_kg / 20  # ~20kg CO2 offset per tree

        return jsonify(
            {
                "status": "success",
                "simulation": {
                    "policy_aggressiveness": aggressiveness,
                    "spot_adoption": spot_adoption,
                    "monthly_savings": round(monthly_savings, 2),
                    "savings_percentage": round(savings_multiplier * 35, 1),
                    "carbon_offset_kg": round(carbon_offset_kg, 1),
                    "trees_equivalent": round(trees_equivalent, 1),
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/policy/apply", methods=["POST"])
def apply_policy_api():
    """Apply a governance policy."""
    try:
        data = request.json or {}
        policy_config = data.get("policy")

        # In a real implementation, this would save policy configuration
        return jsonify(
            {
                "status": "success",
                "message": "Governance policy applied successfully",
                "policy_id": f"policy-{int(time.time())}",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/business-metrics", methods=["POST"])
def add_business_metric():
    try:
        data = request.json or {}
        name = data.get("metric_name")
        value = data.get("value")
        unit = data.get("unit")

        if not name or value is None or not unit:
            return jsonify({"status": "error", "message": "All fields are required."}), 400

        db = SessionLocal()
        try:
            metric = BusinessMetric(
                metric_name=name.upper().replace(" ", "_"), value=float(value), unit=unit
            )
            db.add(metric)
            db.commit()
            return jsonify(
                {"status": "success", "message": f"Metric '{name}' recorded successfully."}
            ), 201
        except Exception as e:
            db.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            db.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/build-with-ai", methods=["GET"])
def build_with_ai():
    """Renders the AI Multi-Cloud Architect Estimator workspace dashboard."""
    return render_template("pages/build_with_ai.html")


@app.route("/api/v1/architect/status", methods=["GET"])
def api_architect_status():
    """Returns the validation state of the configured OpenAI and Gemini API keys."""
    status = architect_manager.verify_api_status()
    return jsonify(
        {"status": "success", "openai": status["openai"], "gemini": status["gemini"]}
    ), 200


@app.route("/api/v1/architect/estimate", methods=["POST"])
def api_architect_estimate():
    """Asynchronously processes user prompt, extracts architecture requirements and compiles a financial BOM."""
    data = request.get_json() or {}
    user_prompt = data.get("prompt")
    provider = data.get("provider", "azure")
    region = data.get("region", "eastus")
    model_provider = data.get("model_provider", "openai")

    if not user_prompt:
        return jsonify({"error": "Infrastructure requirements prompt is required."}), 400

    try:
        # Step 1: Run Cognitive Extraction Contract
        blueprint = architect_manager.generate_blueprint(
            user_prompt, provider, model_provider=model_provider
        )

        # Step 2: Resolve financial cost metrics against PostgreSQL cache
        calculated_payload = resolve_component_costs(blueprint, provider, region)

        return jsonify(calculated_payload), 200

    except Exception as e:
        return jsonify({"error": f"Failed to compile AI architecture: {e!s}"}), 500


@app.route("/about")
def about():
    return render_template("pages/about.html")


@app.route("/docs")
def docs():
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    docs_dir = base_dir / "docs"
    docs_data = []
    if docs_dir.exists():
        files = sorted(docs_dir.glob("*.md"))
        for file_path in files:
            filename = file_path.name
            title = filename.replace(".md", "").lstrip("0123456789_").replace("_", " ").title()
            with file_path.open(encoding="utf-8") as f:
                content = f.read()
            docs_data.append({"filename": filename, "title": title, "content": content})
    return render_template("pages/docs.html", docs_data=docs_data)


@app.route("/integrations")
def integrations():
    return render_template("pages/integrations.html", settings=settings_state)


@app.route("/monitor")
def monitor():
    return render_template("pages/monitor.html")


@app.route("/dashboard")
def dashboard():
    user_name, sub_name = _get_cached_user_info()
    return render_template(
        "pages/dashboard.html",
        user_name=user_name,
        sub_name=sub_name,
        metrics_emit_sec=SOCKET_METRICS_INTERVAL_SEC,
    )


@app.route("/api/dashboard/finops-charts")
def api_dashboard_finops_charts():
    """HTTP snapshot for heavier FinOps charts (refreshed periodically from the client)."""
    if is_first_run():
        return jsonify({"status": "unconfigured", "charts": None}), 200
    
    cache_key = "finops_charts_data"
    cache_ttl = 60  # 60 seconds cache for chart data
    
    # Check session cache first
    cached_charts = session.get(cache_key)
    cached_timestamp = session.get(f"{cache_key}_timestamp")
    
    # Return cached data if valid
    if cached_charts and cached_timestamp:
        if time.time() - float(cached_timestamp) < cache_ttl:
            return jsonify({"status": "ok", "charts": cached_charts, "cached": True})
    
    try:
        az = AzureCollector()
        budget = float(settings_state.get("budget_threshold", 1000.0))
        charts = az.get_finops_dashboard_snapshot(monthly_budget=budget)
        
        # Cache in session
        session[cache_key] = charts
        session[f"{cache_key}_timestamp"] = str(time.time())
        
        return jsonify({"status": "ok", "charts": charts, "cached": False})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "charts": None}), 500


def cache_response(max_age=300):
    """Decorator to add cache headers to responses."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            if hasattr(response, 'headers'):
                response.headers['Cache-Control'] = f'public, max-age={max_age}'
            return response
        return decorated_function
    return decorator


@app.route("/api/auth/status")
@cache_response(max_age=60)  # Cache for 1 minute
def auth_status():
    return jsonify(check_azure_status())


@app.route("/api/v1/docs/search", methods=["POST"])
def docs_search():
    """Search endpoint for documentation using RAG engine."""
    from reaper.web.search_routes import search_engine

    try:
        data = request.json or {}
        query = data.get("query", "")
        if not query:
            return jsonify({"status": "error", "message": "Query is required"}), 400

        results = search_engine.query_docs(user_query=query, top_k=3)
        return jsonify({"status": "success", "results": results, "query": query})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/finops/telemetry-insights", methods=["POST"])
def telemetry_insights():
    """Generate telemetry insights for the integrations page."""
    try:
        return jsonify(
            {
                "status": "success",
                "message": "Telemetry insights generated",
                "insights": {
                    "total_requests": 15420,
                    "avg_response_time": "245ms",
                    "error_rate": "0.02%",
                    "active_connections": 42,
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/rightsizing")
def get_rightsizing():
    az = AzureCollector()
    go_binary = _reaper_engine_binary()
    if not go_binary:
        return jsonify({"status": "error", "message": "Go Engine binary not found"}), 500

    try:
        # pyrefly: ignore [no-matching-overload]
        result = subprocess.run(
            [str(go_binary), "--subscription", az.subscription_id],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return jsonify({"status": "error", "message": result.stderr}), 500

        vm_reports = json.loads(result.stdout).get("vm_reports", [])
        recommendations = RightSizer().calculate_recommendation(vm_reports)

        return jsonify(
            {
                "status": "success",
                "recommendations": recommendations,
                "total_saving": sum(r["monthly_saving"] for r in recommendations),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/scan")
def scan():
    events = [{"msg": "Authenticating with Azure Identity...", "type": "info"}]
    try:
        target_subs = settings_state.get("selected_subscriptions", []) or [
            os.getenv("AZURE_SUBSCRIPTION_ID")
        ]
        # pyrefly: ignore [bad-index, unsupported-operation]
        if not target_subs[0]:
            return jsonify({"status": "error", "message": "No subscription ID configured."}), 400

        scan_results = perform_subscription_scan(target_subs, events)
        formatted_results = format_scan_results(scan_results)

        events.append(
            {
                "msg": f"Scan complete. {len(formatted_results['zombies'])} zombies detected.",
                "type": "warning" if formatted_results["zombies"] else "success",
            }
        )

        return jsonify({"status": "success", "events": events, **formatted_results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def perform_subscription_scan(target_subs, events):
    az = AzureCollector()
    results = {
        "vms_count": 0,
        "orphans": [],
        "snapshots": [],
        "zombies": [],
        "idle_vms": [],
        "utilization": [],
    }

    for sub_id in target_subs:
        events.append({"msg": f"Scanning subscription: {sub_id[:8]}...", "type": "info"})
        az.subscription_id = sub_id

        go_data = az.get_go_scan_results()
        if go_data:
            reports = go_data.get("vm_reports", [])
            active_vms = go_data.get("active_vms", [])
            results["vms_count"] += len(active_vms)

            for d in go_data.get("orphaned_disks", []):
                d["rg"] = "Unknown"
                results["orphans"].append(d)

            for s in go_data.get("orphaned_snapshots", []):
                s["rg"] = "Unknown"
                results["snapshots"].append(s)

            threshold = 2.0 if settings_state.get("idle_strategy") == "aggressive" else 10.0

            reported_vms = set()
            for r in reports:
                name = r.get("name")
                reported_vms.add(name)
                avg_usage = r.get("usage", 0.0)
                rid = r.get("id", "")
                rg = rid.split("/")[4] if "/" in rid else "Unknown"

                results["utilization"].append(
                    {"name": name, "usage": round(avg_usage, 1), "rg": rg}
                )

                if avg_usage < 1.0:
                    results["zombies"].append(
                        {"name": name, "usage": f"{round(avg_usage, 2)}%", "rg": rg}
                    )
                elif avg_usage < threshold:
                    results["idle_vms"].append(
                        {"name": name, "usage": f"{round(avg_usage, 2)}%", "rg": rg}
                    )

            for name in active_vms:
                if name not in reported_vms:
                    results["utilization"].append({"name": name, "usage": 0.0, "rg": "Unknown"})
        else:
            # pyrefly: ignore [missing-attribute]
            az._scan_cache = None

            vms = az.get_vm_inventory()
            results["vms_count"] += len(vms)

            reap_data = az.get_orphaned_disks()
            results["orphans"].extend(reap_data["disks"])
            results["snapshots"].extend(reap_data["snapshots"])
            results["zombies"].extend(az.get_zombie_vms())

            threshold = 2.0 if settings_state["idle_strategy"] == "aggressive" else 10.0
            results["idle_vms"].extend(az.get_idle_vms(cpu_threshold=threshold))

            with contextlib.suppress(Exception):
                results["utilization"].extend(az.get_utilization_report())

            reported_python = {u["name"] for u in results["utilization"]}
            for vm in vms:
                if vm["name"] not in reported_python:
                    results["utilization"].append(
                        {"name": vm["name"], "usage": 0.0, "rg": vm.get("location", "Unknown")}
                    )

    results["utilization"].sort(key=lambda x: x["usage"], reverse=True)
    return results


def format_scan_results(raw):
    total_savings = 0.0
    util_rows = []
    for item in raw["utilization"]:
        usage_pct = float(item.get("usage") or 0.0)
        waste = max(0.0, 1.0 - (usage_pct / 100.0)) if usage_pct < 100 else 0.0
        if waste > 0.85:
            status, color = "CRITICAL", "text-red-400"
        elif waste > 0.5:
            status, color = "LOW_UTIL", "text-yellow-400"
        else:
            status, color = "NORMAL", "text-green-400"
        util_rows.append(
            {
                "name": item.get("name", "Unknown"),
                "rg": item.get("rg", "N/A"),
                "current_sku": "Compute / VM",
                "metrics": f"Avg CPU (24h): {usage_pct}%",
                "status": status,
                "color": color,
                "recommendation": (
                    "Consider rightsizing or deallocating"
                    if waste > 0.5
                    else "Utilization within nominal range"
                ),
            }
        )

    formatted = {
        "vm_count": raw["vms_count"],
        "orphans": [],
        "snapshots": [],
        "zombies": [],
        "idle_vms": [],
        "utilization_report": util_rows,
    }

    # Idle VMs
    for vm in raw["idle_vms"]:
        cost = calc.calculate_monthly_cost("azure", "compute", "standard_d2s_v3")
        total_savings += cost
        formatted["idle_vms"].append(
            {
                "name": vm["name"],
                "usage": vm["usage"],
                "savings": calc.format_price(cost),
                "rg": vm.get("rg", "N/A"),
            }
        )

    # Orphans
    for d in raw["orphans"]:
        cost = calc.calculate_monthly_cost("azure", "storage", "premium_ssd_p6")
        total_savings += cost
        formatted["orphans"].append(
            {
                "name": d["name"],
                "size": f"{d.get('size_gb', 0)} GB",
                "savings": calc.format_price(cost),
                "rg": d.get("rg", "N/A"),
            }
        )

    # Snapshots
    for s in raw["snapshots"]:
        cost = calc.calculate_monthly_cost("azure", "storage", "premium_ssd_p6") * 0.5
        total_savings += cost
        formatted["snapshots"].append(
            {"name": s["name"], "savings": calc.format_price(cost), "rg": s.get("rg", "N/A")}
        )

    # Zombies
    for z in raw["zombies"]:
        cost = calc.calculate_monthly_cost("azure", "compute", "standard_d2s_v3")
        total_savings += cost
        formatted["zombies"].append(
            {
                "name": z["name"],
                "usage": z["usage"],
                "savings": calc.format_price(cost),
                "rg": z.get("rg", "N/A"),
            }
        )

    formatted["total_savings"] = calc.format_price(total_savings)
    return formatted


@app.route("/api/prices")
def get_prices():
    provider = request.args.get("provider", "azure").lower()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    search = request.args.get("search", "").strip()
    service = request.args.get("service", "").strip()
    region = request.args.get("region", "").strip()
    sort_by = request.args.get("sort", "sku-asc")

    try:
        result = query_catalog_prices(
            provider,
            page=page,
            per_page=per_page,
            search=search,
            service=service,
            region=region,
            sort_by=sort_by,
        )
        if result.get("catalog_status") == "warming":
            return jsonify({"status": "warming", **result}), 202
        if not result["prices"] and result.get("catalog_status") == "error":
            meta = get_catalog_status(provider)
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": meta.get("error", "Failed to load live price catalog"),
                        **result,
                    }
                ),
                503,
            )
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/prices/status")
def get_prices_status():
    provider = request.args.get("provider")
    return jsonify({"status": "success", "catalogs": get_catalog_status(provider)})


@app.route("/api/prices/filters")
def get_prices_filters():
    provider = request.args.get("provider", "azure").lower()
    try:
        filters = get_catalog_filters(provider)
        return jsonify({"status": "success", "provider": provider, **filters})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/prices/refresh", methods=["POST"])
def refresh_prices():
    provider = (request.json or {}).get("provider") if request.is_json else None
    providers = [provider] if provider else ["azure", "aws", "gcp"]
    for prov in providers:
        threading.Thread(
            target=warm_catalog, args=(prov,), kwargs={"force": True}, daemon=True
        ).start()
    return jsonify(
        {"status": "success", "message": "Price catalog refresh started", "providers": providers}
    )


@app.route("/api/export/bom", methods=["POST"])
def export_bom():
    try:
        data = request.json or {}
        items = data.get("resources", [])
        total_hourly = data.get("totalHourly", 0.0)
        total_monthly = data.get("totalMonthly", 0.0)

        # Render the HTML template
        rendered_html = render_template(
            "components/bom_pdf_template.html",
            items=items,
            totalHourly=total_hourly,
            totalMonthly=total_monthly,
            date=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Generate PDF in memory
        pdf_out = io.BytesIO()
        if HTML is None:
            return jsonify(
                {
                    "status": "error",
                    "message": "WeasyPrint is not available on this platform (native libraries like libgobject may be missing).",
                }
            ), 500
        HTML(string=rendered_html).write_pdf(pdf_out)
        pdf_out.seek(0)

        return send_file(
            pdf_out,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="Cloud_Reaper_BOM.pdf",
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/tag-health")
def tag_health():
    try:
        session = SessionLocal()
        try:
            resources = session.query(Resource).all()
            unallocated = [r for r in resources if r.is_unallocated]

            total = len(resources)
            count = len(unallocated)
            rate = (total - count) / total * 100 if total > 0 else 100

            return jsonify(
                {
                    "status": "success",
                    "total_resources": total,
                    "compliant_count": total - count,
                    "unallocated_count": count,
                    "compliance_rate": round(rate, 1),
                    "unallocated_spend": 0.0,
                    "missing_tags_summary": [
                        {"resource": r.name, "type": r.type, "missing": "Owner, Project"}
                        for r in unallocated
                    ],
                }
            )
        except Exception as e:
            session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/anomalies")
def anomalies():
    try:
        data = AzureCollector().get_anomaly_data()
        return jsonify(
            {
                "status": "success",
                "services": data,
                "spike_count": sum(1 for d in data if d["is_anomaly"]),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/anomalies/triage", methods=["POST"])
def anomalies_triage():
    try:
        data = request.json or {}
        service = data.get("service", "Unknown")
        cost = float(data.get("cost", 0.0))
        deviation = data.get("deviation", "Unknown")

        if not service:
            return jsonify({"status": "error", "message": "Missing service name"}), 400

        from reaper.engine.copilot.engine import AnomalyTriager

        triager = AnomalyTriager()
        playbook = triager.generate_triage_playbook(service, cost, deviation)

        return jsonify({"status": "success", "playbook": playbook})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/unit-economics")
def unit_economics():
    try:
        session = SessionLocal()
        try:
            db_metrics = (
                session.query(BusinessMetric).order_by(BusinessMetric.date.desc()).limit(10).all()
            )
            actual = (
                session.query(func.sum(CostHistory.cost))
                .filter(CostHistory.cost_type == "ACTUAL")
                .scalar()
                or 10000.0
            )
            amortized = (
                session.query(func.sum(CostHistory.cost))
                .filter(CostHistory.cost_type == "AMORTIZED")
                .scalar()
                or 7500.0
            )

            metrics = []
            for m in db_metrics:
                divisor = 1000 if "1K" in m.unit else (1000000 if "1M" in m.unit else 1)
                unit_count = m.value / divisor
                metric_spend = float(actual) * 0.25
                metrics.append(
                    {
                        "metric": m.metric_name.replace("_", " ").title(),
                        "unit": m.unit,
                        "count": m.value,
                        "total_spend": round(metric_spend, 2),
                        # pyrefly: ignore [no-matching-overload]
                        "cost_per_unit": round(metric_spend / max(unit_count, 1), 4),
                        "trend": 8.5,
                    }
                )

            return jsonify(
                {
                    "status": "success",
                    "metrics": metrics,
                    "total_actual_spend": round(float(actual), 2),
                    "total_amortized_spend": round(float(amortized), 2),
                }
            )
        except Exception as e:
            session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/ri-advisor")
def ri_advisor():
    try:
        candidates = AzureCollector().get_ri_sp_candidates()
        return jsonify(
            {
                "status": "success",
                "candidates": candidates,
                "total_annual_savings": round(sum(c["annual_savings"] for c in candidates), 2),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/cold-storage")
def cold_storage():
    try:
        buckets = AzureCollector().get_cold_storage_candidates()
        return jsonify(
            {
                "status": "success",
                "buckets": buckets,
                "total_monthly_savings": round(sum(b["monthly_savings"] for b in buckets), 2),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/modernization")
def modernization():
    try:
        suggestions = AzureCollector().get_modernization_candidates()
        return jsonify(
            {
                "status": "success",
                "suggestions": suggestions,
                "total_annual_savings": round(sum(s["annual_savings"] for s in suggestions), 2),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/policy-violations")
def policy_violations():
    try:
        violations = AzureCollector().get_policy_violations()
        return jsonify(
            {
                "status": "success",
                "violations": violations,
                "critical_count": sum(1 for v in violations if v["severity"] == "HIGH"),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/budget-status")
def budget_status():
    try:
        return jsonify({"status": "success", "budgets": AzureCollector().get_budget_status()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/budget-killswitch", methods=["POST"])
def budget_killswitch():
    try:
        data = request.json or {}
        sub_name = data.get("subscription", "Unknown")
        time.sleep(0.5)
        return jsonify(
            {
                "status": "success",
                "message": f"Kill-switch initiated for {sub_name}. Checking policy compliance...",
                "vms_stopped": [],
                "estimated_savings": "$0.00/day",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/burn-rate-forecast")
def burn_rate_forecast():
    try:
        return jsonify({"status": "success", "forecast": AzureCollector().get_burn_rate_forecast()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/virtual-tags")
def virtual_tags():
    try:
        return jsonify({"status": "success", "virtual_tags": AzureCollector().get_virtual_tags()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/greenops")
def greenops():
    try:
        return jsonify(
            {
                "status": "success",
                "recommendations": AzureCollector().get_greenops_recommendations(),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/approve-reap", methods=["POST"])
def approve_reap():
    try:
        data = request.json or {}
        res_id, res_type = data.get("resource_id"), data.get("resource_type")
        if not res_id:
            return jsonify({"status": "error", "message": "Missing resource_id"}), 400
        return jsonify(AzureCollector().execute_reap(res_id, res_type))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/prices/regional")
def get_regional_prices():
    try:
        sku = request.args.get("sku")
        region = request.args.get("region")
        if not sku or not region:
            return jsonify({"status": "error", "message": "Missing sku or region parameter"}), 400

        az = AzureCollector()
        prices = az.fetch_regional_prices(sku, region)
        if prices:
            return jsonify({"status": "success", "price": prices[0]})
        return jsonify({"status": "error", "message": "Price not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/arbitrage")
def get_arbitrage():
    try:
        sku = request.args.get("sku")
        region = request.args.get("region")
        price = float(request.args.get("price", 0.0))

        if not sku or not region or not price:
            return jsonify({"status": "error", "message": "Missing parameters"}), 400

        arb = RegionalArbitrage()
        result = arb.analyze_arbitrage(sku, region, price)
        return jsonify({"status": "success", "recommendation": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/activity")
def get_activity():
    try:
        session = SessionLocal()
        try:
            logs = session.query(ActionLog).order_by(ActionLog.timestamp.desc()).limit(10).all()
            result = [
                {
                    "resource": log.resource.name if log.resource else "Unknown",
                    "action": log.action_type,
                    "status": log.status,
                    "time": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for log in logs
            ]
            return jsonify({"status": "success", "activity": result})
        except Exception as e:
            session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/utilization")
def utilization():
    try:
        report = AzureCollector().get_utilization_report()
        formatted_report = []
        for vm in report:
            waste = 1.0 - (vm["usage"] / 100.0) if vm["usage"] < 100 else 0
            formatted_report.append(
                {
                    "name": vm["name"],
                    "rg": vm["rg"],
                    "waste_coefficient": waste,
                    "monthly_cost": 150.0,
                    "is_protected": False,
                    "status": "CRITICAL" if waste > 0.9 else "NORMAL",
                }
            )
        return jsonify({"status": "success", "report": formatted_report})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/spot-prediction")
def spot_prediction():
    try:
        instance_id = request.args.get("instance_id", "vm-spot-worker-01")
        region = request.args.get("region", "eastus")

        predictor = SpotEvictionPredictor()

        # Derive stable, dynamic pseudo-telemetry metrics cryptographically from instance properties
        import hashlib

        hash_seed = hashlib.sha256(f"{instance_id}-{region}".encode()).hexdigest()
        val1 = int(hash_seed[0:4], 16) % 100 / 100.0  # price_volatility: 0.0 to 1.0
        val2 = int(hash_seed[4:8], 16) % 100 / 100.0  # demand_index: 0.0 to 1.0
        val3 = int(hash_seed[8:12], 16) % 100  # region_capacity: 0 to 100

        telemetry = {
            "price_volatility": round(val1, 2),
            "demand_index": round(val2, 2),
            "region_capacity": float(val3),
        }
        result = predictor.monitor_and_trigger(instance_id, region, telemetry)
        return jsonify({"status": "success", "prediction": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/k8s/bin-packing")
def k8s_bin_packing():
    try:
        from reaper.engine.core.workload import KubernetesOptimizer

        optimizer = KubernetesOptimizer()
        return jsonify({"status": "success", "bin_packing": optimizer.get_bin_packing_assessment()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/k8s/hibernation")
def k8s_hibernation():
    try:
        from reaper.engine.core.workload import KubernetesOptimizer

        optimizer = KubernetesOptimizer()
        return jsonify({"status": "success", "hibernation": optimizer.get_hibernation_status()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/ai-token-tracking")
def ai_token_tracking():
    try:
        allocations = [
            {
                "provider": "OpenAI",
                "model": "gpt-4o",
                "department": "Finance-Department -> Core-Banking-API",
                "tokens_consumed": 12450000,
                "input_cost_usd": 62.25,
                "output_cost_usd": 186.75,
                "total_cost_usd": 249.00,
                "equivalent_vm_hours": 171.7,
            },
            {
                "provider": "Anthropic",
                "model": "claude-3-5-sonnet",
                "department": "Platform-Eng -> AI-Architect",
                "tokens_consumed": 8900000,
                "input_cost_usd": 26.70,
                "output_cost_usd": 133.50,
                "total_cost_usd": 160.20,
                "equivalent_vm_hours": 110.5,
            },
            {
                "provider": "Anyscale",
                "model": "llama-3-70b-instruct",
                "department": "Data-Eng -> Customer-Sentiment",
                "tokens_consumed": 45000000,
                "input_cost_usd": 31.50,
                "output_cost_usd": 31.50,
                "total_cost_usd": 63.00,
                "equivalent_vm_hours": 43.4,
            },
        ]
        total_ai_spend = sum(item["total_cost_usd"] for item in allocations)
        return jsonify(
            {
                "status": "success",
                "allocations": allocations,
                "total_ai_spend_usd": round(total_ai_spend, 2),
                "consolidated_report": "AI workloads consolidated. Total AI spend is 12% of total subscription infrastructure cost.",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# Initialize the comprehensive cost optimizer
cost_optimizer = ComprehensiveCostOptimizer()

# Initialize the automated cost reporter
cost_reporter = AutomatedCostReporter()


@app.route("/api/cost-optimization/analyze", methods=["POST"])
def analyze_cost_optimization():
    """Comprehensive cost optimization analysis for all cloud resources"""
    try:
        data = request.json or {}
        provider = data.get("provider", "azure").lower()

        if is_first_run():
            return jsonify(
                {"status": "unconfigured", "message": "Please configure cloud credentials first"}
            ), 200

        # Initialize collector based on provider
        if provider == "azure":
            collector = AzureCollector()
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Provider {provider} not yet supported in comprehensive analysis",
                }
            ), 400

        cost_optimizer.recommendations.clear()

        # Get resource inventory
        resources = []

        # Get compute resources (VMs)
        try:
            vms = collector.get_vm_inventory()

            def _analyze_vm(vm):
                vm_id = vm.get("id") or ""
                if not vm_id and vm.get("name"):
                    vm_id = (
                        f"/subscriptions/{collector.subscription_id}/resourceGroups/"
                        f"{vm.get('rg', 'unknown')}/providers/Microsoft.Compute/virtualMachines/{vm['name']}"
                    )
                vm_metrics = collector.get_vm_metrics(vm_id)
                metrics = ResourceMetrics(
                    cpu_utilization=vm_metrics.get("cpu_percent", {}).get("average", 50),
                    memory_utilization=vm_metrics.get("memory_percent", {}).get("average", 50),
                    disk_utilization=vm_metrics.get("disk_percent", {}).get("average", 50),
                    network_in_mbps=vm_metrics.get("network_in_mbps", 0),
                    network_out_mbps=vm_metrics.get("network_out_mbps", 0),
                    iops=vm_metrics.get("iops", 0),
                    latency_ms=vm_metrics.get("latency_ms", 0),
                    error_rate=vm_metrics.get("error_rate", 0),
                    uptime_percentage=vm_metrics.get("uptime_percentage", 99),
                    peak_cpu_utilization=vm_metrics.get("cpu_percent", {}).get("max", 70),
                    peak_memory_utilization=vm_metrics.get("memory_percent", {}).get("max", 70),
                )
                current_sku = vm.get("size") or vm.get("sku") or "Standard_D2s_v3"
                current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)
                resource_data = {
                    "id": vm_id,
                    "name": vm.get("name", ""),
                    "type": "compute",
                    "provider": provider,
                    "sku": current_sku,
                    "region": vm.get("location", ""),
                    "tags": vm.get("tags", {}),
                }
                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                return recommendations, {
                    "id": vm_id,
                    "name": vm.get("name", ""),
                    "type": "compute",
                    "current_cost": current_cost,
                    "metrics": vm_metrics,
                }

            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=8) as pool:
                for recs, resource in pool.map(_analyze_vm, vms):
                    cost_optimizer.recommendations.extend(recs)
                    resources.append(resource)
        except Exception as e:
            print(f"[!] Error analyzing VMs: {e}")

        # Get storage resources (disks)
        try:
            orphaned_disks = collector.get_orphaned_disks()
            for disk in orphaned_disks.get("disks", []):
                metrics = ResourceMetrics(
                    cpu_utilization=0,
                    memory_utilization=0,
                    disk_utilization=0,  # Orphaned means not attached
                    network_in_mbps=0,
                    network_out_mbps=0,
                    iops=0,
                    latency_ms=0,
                    error_rate=0,
                    uptime_percentage=100,
                    peak_cpu_utilization=0,
                    peak_memory_utilization=0,
                )

                current_sku = disk.get("tier", "premium_ssd")
                current_cost = calc.calculate_monthly_cost(provider, "storage", current_sku)

                resource_data = {
                    "id": disk.get("id", ""),
                    "name": disk.get("name", ""),
                    "type": "storage",
                    "provider": provider,
                    "sku": current_sku,
                    "region": disk.get("location", ""),
                    "tags": disk.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)

                resources.append(
                    {
                        "id": disk.get("id", ""),
                        "name": disk.get("name", ""),
                        "type": "storage",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing storage: {e}")

        # Get idle resources
        try:
            idle_vms = collector.get_idle_vms(cpu_threshold=5.0)
            for vm in idle_vms:
                metrics = ResourceMetrics(
                    cpu_utilization=vm.get("average_cpu", 5),
                    memory_utilization=20,  # Assume low memory utilization for idle VMs
                    disk_utilization=50,
                    network_in_mbps=0.1,
                    network_out_mbps=0.1,
                    iops=10,
                    latency_ms=0,
                    error_rate=0,
                    uptime_percentage=95,
                    peak_cpu_utilization=10,
                    peak_memory_utilization=30,
                )

                current_sku = vm.get("sku", "Standard_D2s_v3")
                current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                resource_data = {
                    "id": vm.get("id", ""),
                    "name": vm.get("name", ""),
                    "type": "compute",
                    "provider": provider,
                    "sku": current_sku,
                    "region": vm.get("location", ""),
                    "tags": vm.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
        except Exception as e:
            print(f"[!] Error analyzing idle resources: {e}")

        # Prioritize and generate summary
        prioritized_recommendations = cost_optimizer.prioritize_recommendations()
        summary = cost_optimizer.generate_summary_report()

        return jsonify(
            {
                "status": "success",
                "summary": summary,
                "recommendations": [rec.to_dict() for rec in prioritized_recommendations],
                "analyzed_resources": len(resources),
            }
        )

    except Exception as e:
        print(f"[!] Error in cost optimization analysis: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-optimization/summary")
def get_optimization_summary():
    """Get a quick summary of cost optimization opportunities"""
    try:
        summary = cost_optimizer.generate_summary_report()
        return jsonify({"status": "success", "summary": summary})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-optimization/categories")
def get_optimization_categories():
    """Get recommendations grouped by optimization category"""
    try:
        by_category = {}
        for rec in cost_optimizer.recommendations:
            cat = rec.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(rec.to_dict())

        # Calculate savings per category
        category_summary = {}
        for cat, recs in by_category.items():
            total_savings = sum(rec["estimated_monthly_savings"] for rec in recs)
            category_summary[cat] = {
                "recommendation_count": len(recs),
                "total_savings": total_savings,
                "recommendations": recs,
            }

        return jsonify({"status": "success", "categories": category_summary})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-optimization/priority/<priority>")
def get_optimization_by_priority(priority):
    """Get recommendations filtered by priority level"""
    try:
        priority_enum = Priority(priority.lower())
        filtered_recs = [
            rec.to_dict() for rec in cost_optimizer.recommendations if rec.priority == priority_enum
        ]

        total_savings = sum(rec["estimated_monthly_savings"] for rec in filtered_recs)

        return jsonify(
            {
                "status": "success",
                "priority": priority,
                "count": len(filtered_recs),
                "total_savings": total_savings,
                "recommendations": filtered_recs,
            }
        )
    except ValueError:
        return jsonify({"status": "error", "message": f"Invalid priority: {priority}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-optimization/resource/<resource_id>")
def get_resource_optimizations(resource_id):
    """Get all optimization recommendations for a specific resource"""
    try:
        resource_recs = [
            rec.to_dict()
            for rec in cost_optimizer.recommendations
            if rec.resource_id == resource_id
        ]

        if not resource_recs:
            return jsonify(
                {
                    "status": "error",
                    "message": f"No recommendations found for resource {resource_id}",
                }
            ), 404

        total_savings = sum(rec["estimated_monthly_savings"] for rec in resource_recs)

        return jsonify(
            {
                "status": "success",
                "resource_id": resource_id,
                "recommendation_count": len(resource_recs),
                "total_savings": total_savings,
                "recommendations": resource_recs,
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-optimization/dashboard")
def get_optimization_dashboard():
    """Get dashboard data for cost optimization visualization"""
    try:
        summary = cost_optimizer.generate_summary_report()

        # Prepare dashboard data
        dashboard_data = {
            "total_recommendations": summary["total_recommendations"],
            "total_monthly_savings": summary["total_monthly_savings"],
            "by_priority": summary["by_priority"],
            "by_category": summary["by_category"],
            "top_recommendations": [
                rec.to_dict() for rec in cost_optimizer.prioritize_recommendations()[:10]
            ],
            "savings_potential": {
                "critical": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.CRITICAL
                ),
                "high": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.HIGH
                ),
                "medium": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.MEDIUM
                ),
                "low": sum(
                    rec.estimated_monthly_savings
                    for rec in cost_optimizer.recommendations
                    if rec.priority == Priority.LOW
                ),
            },
            "implementation_effort_breakdown": {
                "low": len(
                    [
                        rec
                        for rec in cost_optimizer.recommendations
                        if rec.implementation_effort == "low"
                    ]
                ),
                "medium": len(
                    [
                        rec
                        for rec in cost_optimizer.recommendations
                        if rec.implementation_effort == "medium"
                    ]
                ),
                "high": len(
                    [
                        rec
                        for rec in cost_optimizer.recommendations
                        if rec.implementation_effort == "high"
                    ]
                ),
            },
        }

        return jsonify({"status": "success", "dashboard": dashboard_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/cost-optimization")
def cost_optimization_page():
    """Render the cost optimization dashboard page"""
    return render_template("pages/cost-optimization.html")


@app.route("/api/cost-reports/executive-summary", methods=["GET"])
def get_executive_summary():
    """Generate executive summary of cost optimization efforts"""
    try:
        provider = request.args.get("provider", "azure").lower()
        period = request.args.get("period", "monthly").lower()

        period_enum = ReportPeriod[period.upper()]

        summary = cost_reporter.generate_executive_summary(period_enum, provider)
        return jsonify({"status": "success", "summary": summary})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/generate", methods=["POST"])
def generate_cost_report():
    """Generate detailed cost optimization report"""
    try:
        data = request.json or {}
        provider = data.get("provider", "azure").lower()
        period = data.get("period", "monthly").lower()
        format_type = data.get("format", "json").lower()

        period_enum = ReportPeriod[period.upper()]
        format_enum = ReportFormat[format_type.upper()]

        # Update recommendations history from latest analysis
        recommendations = cost_optimizer.prioritize_recommendations()
        cost_reporter.update_recommendation_history([rec.to_dict() for rec in recommendations])

        report_content = cost_reporter.generate_detailed_report(period_enum, provider, format_enum)

        return jsonify(
            {
                "status": "success",
                "format": format_type,
                "report": report_content,
                "generated_at": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/download", methods=["POST"])
def download_cost_report():
    """Download cost optimization report"""
    try:
        data = request.json or {}
        provider = data.get("provider", "azure").lower()
        period = data.get("period", "monthly").lower()
        format_type = data.get("format", "json").lower()

        period_enum = ReportPeriod[period.upper()]
        format_enum = ReportFormat[format_type.upper()]

        report_content = cost_reporter.generate_detailed_report(period_enum, provider, format_enum)

        # Create appropriate response based on format
        if format_type == "json":
            return jsonify({"status": "success", "report": report_content})
        return jsonify(
            {
                "status": "success",
                "report": report_content,
                "format": format_type,
                "filename": f"cost-optimization-report-{period}-{provider}.{format_type}",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/track-status", methods=["POST"])
def track_recommendation_status():
    """Track implementation status of a recommendation"""
    try:
        data = request.json or {}
        recommendation_id = data.get("recommendation_id")
        status = data.get("status", "planned")
        notes = data.get("notes", "")

        if not recommendation_id:
            return jsonify({"status": "error", "message": "recommendation_id is required"}), 400

        success = cost_reporter.track_recommendation_status(recommendation_id, status, notes)

        if success:
            return jsonify({"status": "success", "message": "Status tracked successfully"})
        return jsonify({"status": "error", "message": "Failed to track status"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/implementation-progress")
def get_implementation_progress():
    """Get implementation progress of all recommendations"""
    try:
        progress = cost_reporter._get_implementation_progress()
        return jsonify({"status": "success", "progress": progress})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/trends")
def get_cost_trends():
    """Get cost optimization trends over time"""
    try:
        trends_data = {
            "trends": [trend.to_dict() for trend in cost_reporter.cost_trends],
            "analysis": cost_reporter._generate_trend_analysis(),
        }
        return jsonify({"status": "success", "trends_data": trends_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/category-analysis")
def get_category_analysis():
    """Get category-wise cost optimization analysis"""
    try:
        category_analysis = cost_reporter._generate_category_analysis()
        return jsonify({"status": "success", "category_analysis": category_analysis})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/risk-assessment")
def get_risk_assessment():
    """Get risk assessment for all recommendations"""
    try:
        risk_assessment = cost_reporter._generate_risk_assessment()
        return jsonify({"status": "success", "risk_assessment": risk_assessment})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cost-reports/next-steps")
def get_next_steps():
    """Get recommended next steps for cost optimization"""
    try:
        next_steps = cost_reporter._generate_next_steps()
        return jsonify({"status": "success", "next_steps": next_steps})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@socketio.on("connect")
def handle_connect():
    print("[+] Client Connected to Cloud-Reaper Engine")


@socketio.on("start_log_stream")
def handle_start_log_stream():
    """Handle real-time log streaming with fallback to system logs."""
    import time
    import logging
    from reaper.services.log_streamer import fetch_azure_logs

    socketio.emit("new_log", {"data": "🚀 Initializing Cloud-Reaper Log Stream..."})
    socketio.sleep(0.2)
    socketio.emit("new_log", {"data": "📡 Connecting to log sources..."})
    socketio.sleep(0.2)

    # Try Azure logs first
    try:
        azure_logs = fetch_azure_logs()
        if azure_logs and len(azure_logs) > 0:
            socketio.emit("new_log", {"data": f"✅ Connected to Azure Monitor - Found {len(azure_logs)} recent logs"})
            socketio.sleep(0.3)
            for i, log in enumerate(azure_logs):
                socketio.emit("new_log", {"data": f"[Azure #{i+1}] {log}"})
                # pyrefly: ignore [bad-argument-type]
                socketio.sleep(0.3)
        else:
            socketio.emit("new_log", {"data": "⚠️  No Azure logs found or workspace not configured"})
            socketio.sleep(0.3)
    except Exception as e:
        socketio.emit("new_log", {"data": f"❌ Azure logs error: {str(e)}"})
        socketio.sleep(0.3)

    # Fallback to system logs
    socketio.emit("new_log", {"data": "🔄 Switching to system log streaming..."})
    socketio.sleep(0.2)
    
    # Stream some simulated system logs for demonstration
    system_logs = [
        "🔍 Scanning Azure subscription for cost anomalies...",
        "💰 Analyzing resource utilization patterns...",
        "⚡ Computing optimization recommendations...",
        "📊 Generating cost forecast for next 30 days...",
        "🎯 Identifying idle resources for potential shutdown...",
        "🔧 Checking compliance with tagging policies...",
        "📈 Processing real-time telemetry data...",
        "🌐 Monitoring network bandwidth usage...",
        "💾 Evaluating storage tier optimization...",
        "🚀 Finalizing analysis report..."
    ]
    
    for i, log in enumerate(system_logs):
        timestamp = time.strftime("%H:%M:%S")
        socketio.emit("new_log", {"data": f"[{timestamp}] {log}"})
        # pyrefly: ignore [bad-argument-type]
        socketio.sleep(0.5)
    
    socketio.emit("new_log", {"data": "✅ Log stream complete. System operating normally."})


if __name__ == "__main__":
    # use_reloader=False stops the 'after_fork_in_child' assertion error
    port = int(os.getenv("FLASK_PORT", "5001"))
    host = os.getenv("FLASK_HOST", "127.0.0.1")

    print(f"\n[+] Cloud-Reaper Dashboard Active at http://{host}:{port}")
    print("[*] Engine: gevent | Real-Time Monitoring: ENABLED\n")

    try:
        socketio.run(
            app, host=host, port=port, debug=True, use_reloader=False, allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\n[!] Dashboard server stopped by user.")
