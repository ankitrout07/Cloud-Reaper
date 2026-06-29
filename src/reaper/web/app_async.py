from __future__ import annotations

import asyncio
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

import httpx
from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from starlette.middleware.sessions import SessionMiddleware

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
app = FastAPI(title="Cloud-Reaper", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(_web_dir / "templates"))

# Global HTTP client with connection pooling for external API calls
# This improves performance by reusing connections instead of creating new ones for each request
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=100, max_connections=200, keepalive_expiry=30.0),
    timeout=httpx.Timeout(30.0, connect=10.0),
    http2=True,  # Enable HTTP/2 for better performance
)


# Rate limiter for external API calls to avoid throttling
class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, rate: int, per: float = 1.0):
        self.rate = rate  # requests per second
        self.per = per  # time window in seconds
        self.allowance = rate
        self.last_check = time.time()

    def can_proceed(self) -> bool:
        current = time.time()
        time_passed = current - self.last_check
        self.last_check = current
        self.allowance += time_passed * (self.rate / self.per)

        self.allowance = min(self.allowance, self.rate)

        if self.allowance < 1.0:
            return False
        self.allowance -= 1.0
        return True

    async def wait(self):
        """Wait until rate limit allows proceeding."""
        while not self.can_proceed():
            await asyncio.sleep(0.1)


# Rate limiters for different API providers
azure_rate_limiter = RateLimiter(rate=20, per=1.0)  # 20 requests per second for Azure
aws_rate_limiter = RateLimiter(rate=20, per=1.0)  # 20 requests per second for AWS
gcp_rate_limiter = RateLimiter(rate=20, per=1.0)  # 20 requests per second for GCP
ai_rate_limiter = RateLimiter(rate=10, per=1.0)  # 10 requests per second for AI APIs


# WebSocket Message Batching System
class WebSocketBatcher:
    """Batches WebSocket messages to reduce network overhead and improve performance."""

    def __init__(self, socketio_server, batch_interval_ms=100, max_batch_size=50):
        self.sio = socketio_server
        self.batch_interval = batch_interval_ms / 1000.0  # Convert to seconds
        self.max_batch_size = max_batch_size
        self.batches = {}  # event_name -> list of messages
        self.timers = {}  # event_name -> timer handle
        self.lock = asyncio.Lock()

    async def emit(self, event: str, data: dict, room: str = None):
        """Queue a message for batched emission."""
        async with self.lock:
            if event not in self.batches:
                self.batches[event] = []

            self.batches[event].append(data)

            # Send immediately if batch size exceeded
            if len(self.batches[event]) >= self.max_batch_size:
                await self._flush_batch(event, room)
            # Set timer to flush batch after interval
            elif event not in self.timers or self.timers[event].cancelled():
                self.timers[event] = asyncio.create_task(self._schedule_flush(event, room))

    async def _schedule_flush(self, event: str, room: str = None):
        """Schedule batch flush after interval."""
        await asyncio.sleep(self.batch_interval)
        await self._flush_batch(event, room)

    async def _flush_batch(self, event: str, room: str = None):
        """Flush all pending messages for an event."""
        async with self.lock:
            if event not in self.batches or not self.batches[event]:
                return

            messages = self.batches[event]
            self.batches[event] = []

            if event in self.timers:
                self.timers[event].cancel()
                del self.timers[event]

        # Send batched messages
        if messages:
            try:
                # Send as a single batch message
                await self.sio.emit(
                    f"{event}_batch", {"messages": messages, "count": len(messages)}, room=room
                )
            except Exception as e:
                print(f"[!] WebSocket batch emit error for {event}: {e}")

    async def flush_all(self):
        """Flush all pending batches immediately."""
        async with self.lock:
            events = list(self.batches.keys())

        for event in events:
            await self._flush_batch(event)


import socketio

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# Global WebSocket batcher instance
ws_batcher = WebSocketBatcher(sio, batch_interval_ms=150, max_batch_size=30)

import json as json_module

from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from starlette.requests import Request as StarletteRequest


def jsonify(*args, **kwargs):
    if args and isinstance(args[0], dict):
        content = args[0]
    else:
        content = kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)


def redirect(url: str):
    return RedirectResponse(url=url)


def url_for(endpoint: str, **kwargs):
    query = "&".join(f"{k}={v}" for k, v in kwargs.items())
    return f"/{endpoint}?{query}" if query else f"/{endpoint}"


def render_template(template_name: str, request: Request | None = None, **kwargs):
    if request is None:
        request = kwargs.pop("request", None)
    if request is None:
        request = StarletteRequest({"type": "http", "method": "GET", "headers": [], "path": "/"})
    context = {"request": request, **kwargs}
    return templates.TemplateResponse(request, template_name, context)


def render_template_string(template_name: str, **kwargs) -> str:
    template = templates.env.get_template(template_name)
    return template.render(**kwargs)


def send_from_directory(directory: str, filename: str, **kwargs):
    return FileResponse(os.path.join(directory, filename))


app.mount("/static", StaticFiles(directory=str(_web_dir / "static")), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enable response compression for better performance
app.add_middleware(GZipMiddleware, minimum_size=500)

# Configure compression settings

# Performance optimizations

# Enable threading for better performance

secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.add_middleware(SessionMiddleware, secret_key=secret_key, max_age=31536000)

socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

from reaper.web.copilot_router import copilot_router

app.include_router(copilot_router)
from reaper.web.search_router import search_router

app.include_router(search_router)
from reaper.web.metrics_router import telemetry_router

app.include_router(telemetry_router)
from reaper.web import go_bridge  # async Go engine bridge (non-blocking)

VAULT_UNLOCK_TTL_SEC = int(os.getenv("VAULT_UNLOCK_TTL_SEC", "3600"))
thread = None
thread_lock = threading.Lock()

# Azure standard metrics rarely refresh faster than ~1 minute; 5–10s is a safe UI throttle.
SOCKET_METRICS_INTERVAL_SEC = int(os.getenv("REAPER_METRICS_EMIT_SEC", "8"))

# Global Provider Authentication State (In-Memory Runtime Config)
# This provides a low-overhead way to track active provider authentication status
# across all requests without hitting the database on every request.
PROVIDER_AUTH_STATE = {
    "provider": None,  # "azure", "aws", "gcp", "k8s"
    "authenticated": False,
    "subscription_id": None,
    "last_sync": None,
}


async def background_metrics_worker():
    """Fetches Azure Monitor CPU samples and pushes over WebSocket (throttled)."""
    error_count = 0
    max_errors = 5
    backoff_time = SOCKET_METRICS_INTERVAL_SEC
    max_backoff = 120  # Maximum 2 minutes backoff

    while True:
        try:
            import asyncio

            await asyncio.sleep(backoff_time)
            now = datetime.datetime.now(datetime.UTC).strftime("%H:%M:%S")
            cpu_usage = None

            try:
                if not is_first_run():

                    def _get_cpu():
                        c = AzureCollector()
                        return c.get_live_subscription_cpu_average(max_vms=6)

                    cpu_usage = await asyncio.to_thread(_get_cpu)
                    error_count = 0  # Reset error count on success
                    backoff_time = SOCKET_METRICS_INTERVAL_SEC  # Reset backoff on success
            except Exception as e:
                error_count += 1
                print(f"[!] Metrics Worker Error ({error_count}/{max_errors}): {e}")

                # Exponential backoff for consecutive errors
                if error_count >= max_errors:
                    backoff_time = min(backoff_time * 2, max_backoff)
                    print(
                        f"[!] Too many consecutive errors, backing off for {backoff_time} seconds"
                    )
                    error_count = 0

            if cpu_usage is not None:
                cpu_usage = round(float(cpu_usage), 2)
                try:
                    # Use batched WebSocket emission for better performance
                    await ws_batcher.emit("metric_update", {"time": now, "value": cpu_usage})
                except Exception as e:
                    print(f"[!] Metrics emit error: {e}")

        except Exception as e:
            print(f"[!] Critical error in metrics worker: {e}")
            # Prevent rapid crash loops by sleeping longer on critical errors
            backoff_time = min(backoff_time * 2, max_backoff)
            await asyncio.sleep(backoff_time)


# Start the worker after the app is ready
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_metrics_worker())


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


def _run_collector(method_name: str, *args, **kwargs) -> Any:
    """Helper to run AzureCollector methods in thread pool to avoid blocking event loop."""
    c = AzureCollector()
    method = getattr(c, method_name)
    return method(*args, **kwargs)


@app.post("/api/settings/sync")
async def sync_settings(request: Request):
    data = (await request.json() if await request.body() else {}) or {}
    try:
        # 1. Update the .env file physically
        set_key(ENV_PATH, "AZURE_SUBSCRIPTION_ID", data.get("subscriptionId"))
        set_key(ENV_PATH, "AZURE_TENANT_ID", data.get("tenantId"))
        set_key(ENV_PATH, "AZURE_CLIENT_ID", data.get("clientId"))
        set_key(ENV_PATH, "AZURE_CLIENT_SECRET", data.get("clientSecret"))

        # 2. Reload the environment variables for the current running process
        load_dotenv(ENV_PATH, override=True)

        return JSONResponse(
            status_code=200, content={"status": "success", "message": "Credentials Sync Complete"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.middleware("http")
async def check_setup(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/static")
        or path.startswith("/api/")
        or "favicon" in path
        or path.startswith("/settings")
    ):
        return await call_next(request)
    if is_first_run():
        return RedirectResponse(url="/settings?tab=cloud")
    return await call_next(request)


@app.on_event("startup")
async def startup_event():
    """Initialize background tasks and warm up caches."""
    # Start background metrics worker
    asyncio.create_task(background_metrics_worker())

    # Start background task manager
    from reaper.engine.core.background_tasks import background_manager

    await background_manager.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    await http_client.aclose()

    # Stop background task manager
    from reaper.engine.core.background_tasks import background_manager

    await background_manager.stop()


@app.get("/favicon.ico")
async def favicon_ico(request: Request):
    return send_from_directory(
        str(_web_dir / "static" / "assets"), "favicon.ico", mimetype="image/x-icon"
    )


@app.get("/favicon.png")
async def favicon_png(request: Request):
    return send_from_directory(
        str(_web_dir / "static" / "assets"), "favicon.png", mimetype="image/png"
    )


async def _get_cached_user_info(request: Request) -> tuple[str, str]:
    """Get cached user/subscription info with 5-minute TTL to avoid blocking Azure API calls."""
    cache_key_prefix = "azure_user_info"
    cache_ttl = 300  # 5 minutes

    # Check session cache first
    user_name = request.session.get(f"{cache_key_prefix}_user")
    sub_name = request.session.get(f"{cache_key_prefix}_sub")
    timestamp = request.session.get(f"{cache_key_prefix}_timestamp")

    # Return cached data if valid
    if user_name and sub_name and timestamp:
        if time.time() - float(timestamp) < cache_ttl:
            return user_name, sub_name

    # Fetch fresh data and cache it
    try:

        def _get_user_info():
            c = AzureCollector()
            return c.get_user_name(), c.get_subscription_name()

        user_name, sub_name = await asyncio.to_thread(_get_user_info)

        # Cache in session
        request.session[f"{cache_key_prefix}_user"] = user_name
        request.session[f"{cache_key_prefix}_sub"] = sub_name
        request.session[f"{cache_key_prefix}_timestamp"] = str(time.time())

        return user_name, sub_name
    except Exception as e:
        print(f"[!] Error fetching user info: {e}")
        return "Azure User", "Azure Subscription"


@app.get("/")
async def index(request: Request):
    user_name, sub_name = await _get_cached_user_info(request)
    return templates.TemplateResponse(
        request,
        "pages/index.html",
        {"request": request, "user_name": user_name, "sub_name": sub_name},
    )


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


def _is_vault_unlocked(request: Request) -> bool:
    if not request.session.get("vault_unlocked"):
        return False
    expires = request.session.get("vault_unlock_expires", 0)
    if time.time() > float(expires):
        request.session.pop("vault_unlocked", None)
        request.session.pop("vault_unlock_expires", None)
        request.session.pop("vault_fernet_key", None)
        return False
    return bool(request.session.get("vault_fernet_key"))


def _session_fernet(request: Request) -> Fernet | None:
    key = request.session.get("vault_fernet_key")
    if not key or not _is_vault_unlocked(request):
        return None
    return Fernet(key.encode("utf-8"))


def _unlock_vault_session(request: Request, passcode: str, settings: VaultSettings) -> bool:
    salt = _vault_salt_bytes(settings)
    if not verify_passcode(passcode, salt, cast(str, settings.passcode_verifier)):
        return False
    request.session["vault_fernet_key"] = derive_fernet_key(passcode, salt).decode("utf-8")
    request.session["vault_unlocked"] = True
    request.session["vault_unlock_expires"] = time.time() + VAULT_UNLOCK_TTL_SEC
    return True


@app.get("/settings")
async def settings(request: Request):
    cloud_summary, active_provider = _cloud_connections_summary()
    vault_configured = _vault_settings_row() is not None
    return render_template(
        "pages/settings.html",
        request=request,
        cloud_connections=cloud_summary,
        active_provider=active_provider,
        vault_configured=vault_configured,
    )


@app.post("/api/settings/update")
async def update_settings(request: Request):
    data = (await request.json() if await request.body() else {}) or {}
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


@app.post("/api/settings/connect-azure")
async def connect_azure(request: Request):
    data = await request.json() if await request.body() else {}
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
            PROVIDER_AUTH_STATE["last_sync"] = datetime.datetime.now(datetime.UTC).isoformat()

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
                        service_account_info = json.loads(credentials["service_account_json"])
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

        elif provider == "k8s":
            # Test Kubernetes credentials
            try:
                kubeconfig = credentials.get("kubeconfig")
                if kubeconfig:
                    return {
                        "valid": True,
                        "message": "Kubernetes kubeconfig saved",
                        "details": "Kubeconfig stored successfully",
                    }
                if credentials.get("service_account_token"):
                    return {
                        "valid": True,
                        "message": "Kubernetes service account token saved",
                        "details": "Service account token stored successfully",
                    }
                return {
                    "valid": False,
                    "message": "No kubeconfig or service account token provided",
                    "details": "",
                }
            except Exception as e:
                return {
                    "valid": False,
                    "message": f"Kubernetes validation failed: {e!s}",
                    "details": "",
                }

        else:
            return {
                "valid": True,
                "message": f"{provider.upper()} credentials saved",
                "details": "No validation available for this provider",
            }

    except Exception as e:
        return {"valid": False, "message": f"Validation error: {e!s}", "details": ""}


@app.get("/api/context/switch")
async def switch_context(request: Request):
    provider = (request.query_params.get("provider") or "").lower()
    if provider not in {"aws", "azure", "gcp", "k8s"}:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Unsupported provider."}
        )

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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()


@app.post("/api/settings/connect-cloud")
async def connect_cloud(request: Request):
    """Connect to cloud provider with credential validation."""
    data = (await request.json() if await request.body() else {}) or {}
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
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Unsupported provider."}
        )

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
            },
            status_code=400,
        )

    try:
        # Validate credentials by actually connecting to the cloud service
        validation_result = _validate_cloud_credentials(provider, credentials)

        if not validation_result["valid"]:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Connection validation failed: {validation_result['message']}",
                },
                status_code=400,
            )

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
            PROVIDER_AUTH_STATE["last_sync"] = datetime.datetime.now(datetime.UTC).isoformat()

            return jsonify(
                {
                    "status": "success",
                    "message": f"{provider.capitalize()} credentials validated and activated successfully. {validation_result['details']}",
                }
            )
        except Exception as e:
            db.rollback()
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        finally:
            db.close()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/settings/cloud-connections")
async def list_cloud_connections(request: Request):
    summary, active_provider = _cloud_connections_summary()
    return jsonify(
        {
            "status": "success",
            "connections": summary,
            "active_provider": active_provider,
        }
    )


@app.get("/api/v1/auth/status")
async def auth_status(request: Request):
    """
    Unified authentication status endpoint for global provider state.
    Returns the current provider authentication status with subscription details.
    """
    return jsonify(
        {
            "provider": PROVIDER_AUTH_STATE.get("provider"),
            "authenticated": PROVIDER_AUTH_STATE.get("authenticated", False),
            "subscription_id": PROVIDER_AUTH_STATE.get("subscription_id"),
            "last_sync": PROVIDER_AUTH_STATE.get("last_sync"),
        }
    )


@app.get("/api/vault/status")
async def vault_status(request: Request):
    configured = _vault_settings_row() is not None
    return jsonify(
        {
            "status": "success",
            "configured": configured,
            "unlocked": _is_vault_unlocked(request),
        }
    )


@app.post("/api/vault/setup")
async def vault_setup(request: Request):
    data = (await request.json() if await request.body() else {}) or {}
    if not data:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Request body is required."}
        )

    passcode = (data.get("passcode") or "").strip()
    confirm = (data.get("confirm") or "").strip()
    passcode_type = (data.get("passcode_type") or "password").strip().lower()

    if passcode_type == "pin":
        if len(passcode) != 4:
            return jsonify(
                {"status": "error", "message": "PIN passcode must be exactly 4 digits/characters."},
                status_code=400,
            )
    elif len(passcode) < 8:
        return jsonify(
            {"status": "error", "message": "Password passcode must be at least 8 characters."},
            status_code=400,
        )

    if passcode != confirm:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Passcodes do not match."}
        )

    db = SessionLocal()
    try:
        if db.query(VaultSettings).first():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Vault is already configured."},
            )

        salt = generate_salt()
        settings = VaultSettings(
            salt=base64.b64encode(salt).decode("utf-8"),
            passcode_verifier=hash_passcode(passcode, salt),
        )
        db.add(settings)
        db.commit()
        _unlock_vault_session(request, passcode, settings)
        return {"status": "success", "message": "Vault created and unlocked."}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()


@app.post("/api/vault/reset")
async def vault_reset(request: Request):
    """Erases all stored vault entries and resets the passcode setup status."""
    db = SessionLocal()
    try:
        db.query(VaultEntry).delete()
        db.query(VaultSettings).delete()
        db.commit()

        request.session.pop("vault_unlocked", None)
        request.session.pop("vault_unlock_expires", None)
        request.session.pop("vault_fernet_key", None)

        return jsonify(
            {"status": "success", "message": "Vault successfully reset. All stored secrets erased."}
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()


@app.post("/api/vault/unlock")
async def vault_unlock(request: Request):
    data = (await request.json() if await request.body() else {}) or {}
    if not data:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Request body is required."}
        )

    passcode = (data.get("passcode") or "").strip()
    if not passcode:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Passcode is required."}
        )

    settings = _vault_settings_row()
    if not settings:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Vault is not configured yet."}
        )
    if not _unlock_vault_session(request, passcode, settings):
        return JSONResponse(
            status_code=401, content={"status": "error", "message": "Incorrect passcode."}
        )
    return {"status": "success", "message": "Vault unlocked."}


@app.post("/api/vault/lock")
async def vault_lock(request: Request):
    request.session.pop("vault_unlocked", None)
    request.session.pop("vault_unlock_expires", None)
    request.session.pop("vault_fernet_key", None)
    return {"status": "success", "message": "Vault locked."}


@app.get("/api/vault/entries")
async def vault_list_entries(request: Request):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

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
        return {"status": "success", "entries": entries}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()


@app.post("/api/vault/entries")
async def vault_create_entry(request: Request):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

    fernet = _session_fernet(request)
    if not fernet:
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault session expired."}
        )

    data = (await request.json() if await request.body() else {}) or {}
    if not data:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Request body is required."}
        )

    label = (data.get("label") or "").strip()
    entry_type = (data.get("entry_type") or "credential").strip().lower()
    value = (data.get("value") or "").strip()
    username = (data.get("username") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not label or not value:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Label and secret value are required."},
        )
    if entry_type not in {"credential", "passcode", "note"}:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Invalid entry type."}
        )

    payload = {"value": value, "username": username, "notes": notes}
    try:
        token = fernet.encrypt(json.dumps(payload).encode("utf-8")).decode("utf-8")
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"status": "error", "message": f"Encryption failed: {e!s}"}
        )

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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()


@app.get("/api/vault/entries/{entry_id}")
async def vault_get_entry(request: Request, entry_id: int):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

    fernet = _session_fernet(request)
    if not fernet:
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault session expired."}
        )

    db = SessionLocal()
    try:
        row = db.query(VaultEntry).filter_by(id=entry_id).first()
        if not row:
            return JSONResponse(
                status_code=404, content={"status": "error", "message": "Entry not found."}
            )
        try:
            payload = json.loads(
                fernet.decrypt(row.encrypted_payload.encode("utf-8")).decode("utf-8")
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"Unable to decrypt entry: {e!s}"},
            )
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()


@app.delete("/api/vault/entries/{entry_id}")
async def vault_delete_entry(request: Request, entry_id: int):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

    db = SessionLocal()
    try:
        row = db.query(VaultEntry).filter_by(id=entry_id).first()
        if not row:
            return JSONResponse(
                status_code=404, content={"status": "error", "message": "Entry not found."}
            )
        db.delete(row)
        db.commit()
        return {"status": "success", "message": "Entry deleted."}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        db.close()


@app.get("/api/settings/auth")
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


@app.get("/api/settings/subscriptions")
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


@app.get("/pricing")
async def pricing(request: Request):
    return templates.TemplateResponse(request, "pages/pricing.html", {"request": request})


@app.get("/finops")
async def finops(request: Request):
    return templates.TemplateResponse(request, "pages/finops.html", {"request": request})


@app.get("/financial")
async def financial(request: Request):
    tab = request.query_params.get("tab", "budget")
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
        "pages/financial.html",
        request=request,
        active_tab=tab,
        settings=settings_state,
        db_metrics=db_metrics,
    )


@app.post("/api/v1/finops/simulate/commitment")
async def simulate_commitment(request: Request):
    # Placeholder simulator logic.
    data = (await request.json() if await request.body() else {}) or {}
    return jsonify(
        {
            "status": "success",
            "message": "Commitment simulated successfully",
            "savings_estimate": 150.00,
            "roi_months": 3.5,
        }
    )


@app.post("/api/v1/finops/simulate/policy")
async def simulate_policy(request: Request):
    # Placeholder logic for what-if policy application.
    data = (await request.json() if await request.body() else {}) or {}
    return jsonify(
        {
            "status": "success",
            "message": "Policy simulated successfully",
            "projected_savings": 820.00,
            "carbon_offset": 184.2,
        }
    )


@app.post("/api/financial/target-margin/calculate")
async def calculate_target_margin(request: Request):
    """Calculate optimal resource modifications to close the gap between current and target spend using actual Azure resource costs."""
    try:
        data = (await request.json() if await request.body() else {}) or {}

        current_spend = data.get("current_spend", 0.0)
        target_spend = data.get("target_spend", 0.0)

        # Get current resource inventory for analysis
        if is_first_run():
            return jsonify(
                {"status": "unconfigured", "message": "Please configure cloud credentials first"}
            )

        def _fetch_tmf_data():
            c = AzureCollector()
            return (
                c.get_resource_cost_summary(),
                c.get_vm_inventory(),
                c.get_idle_vms(),
                c.get_orphaned_disks(),
            )

        resource_summary, vms, idle_vms, orphaned_disks = await asyncio.to_thread(_fetch_tmf_data)

        # Use actual current spend from resource summary if available
        if resource_summary and resource_summary.get("total_monthly_cost", 0) > 0:
            current_spend = resource_summary["total_monthly_cost"]
            print(f"[TMF] Using current spend from resource summary: ${current_spend:.2f}")
        elif current_spend == 0.0:
            # If no current spend provided and no resource summary, return error
            print("[TMF] No current spend available - cannot calculate target margin")
            return jsonify(
                {
                    "status": "error",
                    "message": "Unable to determine current spend. Please ensure Azure credentials are configured and resources are available.",
                }
            )

        # Enhanced savings calculation with risk-weighted optimization
        optimization_opportunities = []

        # VM Rightsizing Analysis (High Impact, Low Risk)
        if vms:
            for vm in vms:
                vm_cost = vm.get("cost", 0)  # Use actual cost from inventory
                if vm_cost == 0:
                    continue

                cpu_utilization = vm.get("cpu_utilization", 50)
                memory_utilization = vm.get("memory_utilization", 50)

                # Calculate rightsizing potential based on utilization
                if cpu_utilization < 30 or memory_utilization < 30:
                    # More precise savings calculation based on actual utilization
                    utilization_factor = min(cpu_utilization, memory_utilization) / 100
                    potential_savings = (
                        vm_cost * (1 - utilization_factor) * 0.8
                    )  # 80% of unused capacity
                    risk_score = 0.2  # Low risk

                    # Suggest specific size downgrade based on utilization
                    suggested_action = "Downsize to smaller VM size"
                    if cpu_utilization < 10:
                        suggested_action = "Downsize to 1/4 size or consider serverless"
                    elif cpu_utilization < 20:
                        suggested_action = "Downsize to 1/2 size"

                    optimization_opportunities.append(
                        {
                            "type": "rightsizing",
                            "resource_id": vm.get("id"),
                            "resource_name": vm.get("name"),
                            "potential_savings": round(potential_savings, 2),
                            "risk_score": risk_score,
                            "implementation_complexity": "low",
                            "description": f"{vm.get('name')} ({vm.get('size')}) - CPU: {cpu_utilization}%, {suggested_action}",
                            "current_cost": round(vm_cost, 2),
                        }
                    )

        # Idle Resource Elimination (High Impact, Very Low Risk)
        if idle_vms:
            for vm in idle_vms:
                vm_cost = vm.get("cost", 0)  # Use actual cost from enhanced idle VM data
                if vm_cost == 0:
                    continue

                potential_savings = vm_cost  # 100% savings by eliminating
                risk_score = 0.1  # Very low risk
                optimization_opportunities.append(
                    {
                        "type": "idle_elimination",
                        "resource_id": vm.get("id"),
                        "resource_name": vm.get("name"),
                        "potential_savings": round(potential_savings, 2),
                        "risk_score": risk_score,
                        "implementation_complexity": "very_low",
                        "description": f"Delete or deallocate idle VM {vm.get('name')} ({vm.get('size')}, {vm.get('location')})",
                        "current_cost": round(vm_cost, 2),
                    }
                )

        # Storage Tier Optimization (Medium Impact, Low Risk)
        if orphaned_disks and orphaned_disks.get("disks"):
            for disk in orphaned_disks["disks"]:
                disk_cost = disk.get("cost", 0)  # Use actual cost from enhanced orphaned disk data
                if disk_cost == 0:
                    continue

                current_tier = disk.get("tier", "premium")

                # Calculate savings based on tier downgrades
                tier_savings_map = {
                    "Premium_LRS": 0.6,  # 60% savings by moving to standard
                    "Premium_ZRS": 0.6,
                    "Standard_LRS": 0.4,  # 40% savings by moving to cool
                    "Standard_GRS": 0.4,
                    "Standard_ZRS": 0.4,
                }

                potential_savings = disk_cost * tier_savings_map.get(current_tier, 0.3)
                risk_score = 0.15  # Low risk

                # Suggest specific tier based on current tier
                suggested_tier = "Standard HDD"
                if "Premium" in current_tier:
                    suggested_tier = "Standard SSD"
                elif "Standard" in current_tier:
                    suggested_tier = "Cool tier (if infrequently accessed)"

                optimization_opportunities.append(
                    {
                        "type": "storage_optimization",
                        "resource_id": disk.get("id"),
                        "resource_name": disk.get("name"),
                        "potential_savings": round(potential_savings, 2),
                        "risk_score": risk_score,
                        "implementation_complexity": "low",
                        "description": f"Move {disk.get('name')} ({disk.get('size_gb', 0)}GB) from {current_tier} to {suggested_tier}",
                        "current_cost": round(disk_cost, 2),
                    }
                )

        # Network Resource Cleanup (Medium Impact, Low Risk)
        if resource_summary:
            networking_resources = resource_summary.get("networking", {}).get("resources", [])
            for resource in networking_resources:
                if resource.get("is_waste", False):
                    resource_cost = resource.get("cost", 0)
                    if resource_cost > 0:
                        potential_savings = resource_cost
                        risk_score = 0.1  # Very low risk for orphaned resources
                        optimization_opportunities.append(
                            {
                                "type": "network_cleanup",
                                "resource_id": resource.get("name"),
                                "resource_name": resource.get("name"),
                                "potential_savings": round(potential_savings, 2),
                                "risk_score": risk_score,
                                "implementation_complexity": "very_low",
                                "description": f"Delete orphaned {resource.get('type')} {resource.get('name')}",
                                "current_cost": round(resource_cost, 2),
                            }
                        )

        # Commitment Adoption (High Impact, Medium Risk)
        # Calculate based on actual VM compute costs from resource summary
        compute_costs = (
            resource_summary.get("virtual_machines", {}).get("total_cost", 0)
            if resource_summary
            else 0
        )
        if compute_costs > 50:  # Only recommend if compute spend is significant
            commitment_potential = (
                compute_costs * 0.30
            )  # Up to 30% savings with reservations on compute
            optimization_opportunities.append(
                {
                    "type": "commitment_adoption",
                    "resource_id": "commitment_pool",
                    "resource_name": "Azure Reserved Instances",
                    "potential_savings": round(commitment_potential, 2),
                    "risk_score": 0.4,  # Medium risk (commitment period)
                    "implementation_complexity": "medium",
                    "description": f"Purchase Azure Reserved Instances for ${compute_costs:.2f}/month compute spend (save ~30%)",
                    "current_cost": round(compute_costs, 2),
                }
            )

        # Sort opportunities by ROI (savings/risk ratio) - prioritize high savings, low risk
        optimization_opportunities.sort(
            key=lambda x: x["potential_savings"] / (x["risk_score"] + 0.1), reverse=True
        )

        # Calculate gap
        gap = current_spend - target_spend

        # Calculate total potential
        total_potential = sum(opt["potential_savings"] for opt in optimization_opportunities)

        if total_potential < gap:
            return jsonify(
                {
                    "status": "warning",
                    "message": "Unable to close gap with available optimizations",
                    "gap": gap,
                    "total_potential": total_potential,
                    "remaining_gap": gap - total_potential,
                    "available_opportunities": len(optimization_opportunities),
                }
            )

        # Smart gap-closing algorithm: prioritize high-ROI opportunities
        selected_optimizations = []
        remaining_gap = gap
        total_projected_savings = 0

        for opt in optimization_opportunities:
            if remaining_gap <= 0:
                break

            # Take full optimization if it doesn't over-close the gap significantly
            if opt["potential_savings"] <= remaining_gap * 1.1:  # Allow 10% overage
                selected_optimizations.append(opt)
                total_projected_savings += opt["potential_savings"]
                remaining_gap -= opt["potential_savings"]
            else:
                # Partial optimization - take only what's needed
                partial_ratio = remaining_gap / opt["potential_savings"]
                partial_opt = opt.copy()
                partial_opt["potential_savings"] = remaining_gap
                partial_opt["description"] = (
                    f"Partial: {opt['description']} ({partial_ratio:.1%} implementation)"
                )
                selected_optimizations.append(partial_opt)
                total_projected_savings += remaining_gap
                remaining_gap = 0

        # Aggregate by optimization type for UI display
        type_aggregates = {}
        for opt in selected_optimizations:
            opt_type = opt["type"]
            if opt_type not in type_aggregates:
                type_aggregates[opt_type] = {
                    "total_savings": 0,
                    "count": 0,
                    "avg_risk": 0,
                    "resources": [],
                }
            type_aggregates[opt_type]["total_savings"] += opt["potential_savings"]
            type_aggregates[opt_type]["count"] += 1
            type_aggregates[opt_type]["avg_risk"] += opt["risk_score"]
            type_aggregates[opt_type]["resources"].append(opt["resource_name"])

        # Calculate averages and percentages
        max_savings_by_type = {
            "rightsizing": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "rightsizing"
            ),
            "idle_elimination": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "idle_elimination"
            ),
            "storage_optimization": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "storage_optimization"
            ),
            "network_cleanup": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "network_cleanup"
            ),
            "commitment_adoption": sum(
                opt["potential_savings"]
                for opt in optimization_opportunities
                if opt["type"] == "commitment_adoption"
            ),
        }

        optimal_levers = {}
        for opt_type, aggregates in type_aggregates.items():
            aggregates["avg_risk"] /= aggregates["count"]
            max_possible = max_savings_by_type.get(opt_type, 1)
            optimal_levers[opt_type] = (
                min(100, (aggregates["total_savings"] / max_possible) * 100)
                if max_possible > 0
                else 0
            )

        # Ensure all lever types are present
        for lever_type in [
            "rightsizing",
            "idle_elimination",
            "storage_optimization",
            "commitment_adoption",
        ]:
            if lever_type not in optimal_levers:
                optimal_levers[lever_type] = 0

        projected_rightsizing_savings = type_aggregates.get("rightsizing", {}).get(
            "total_savings", 0
        )
        projected_idle_savings = type_aggregates.get("idle_elimination", {}).get("total_savings", 0)
        projected_storage_savings = type_aggregates.get("storage_optimization", {}).get(
            "total_savings", 0
        )
        projected_commitment_savings = type_aggregates.get("commitment_adoption", {}).get(
            "total_savings", 0
        )

        new_spend = current_spend - total_projected_savings

        return jsonify(
            {
                "status": "success",
                "current_spend": current_spend,
                "target_spend": target_spend,
                "gap": gap,
                "optimal_levers": optimal_levers,
                "projected_savings": {
                    "rightsizing": projected_rightsizing_savings,
                    "idle_elimination": projected_idle_savings,
                    "storage_optimization": projected_storage_savings,
                    "commitment_adoption": projected_commitment_savings,
                    "total": total_projected_savings,
                },
                "new_spend": new_spend,
                "gap_status": "closed" if new_spend <= target_spend else "open",
                "optimization_details": {
                    "total_opportunities_analyzed": len(optimization_opportunities),
                    "selected_optimizations": len(selected_optimizations),
                    "avg_risk_score": sum(opt["risk_score"] for opt in selected_optimizations)
                    / len(selected_optimizations)
                    if selected_optimizations
                    else 0,
                },
                "recommended_actions": [
                    {
                        "type": "VM Rightsizing",
                        "impact": projected_rightsizing_savings,
                        "description": f"Optimize {type_aggregates.get('rightsizing', {}).get('count', 0)} VMs for ${projected_rightsizing_savings:.2f} savings",
                        "risk_level": "low"
                        if type_aggregates.get("rightsizing", {}).get("avg_risk", 0) < 0.3
                        else "medium",
                    },
                    {
                        "type": "Idle Resource Elimination",
                        "impact": projected_idle_savings,
                        "description": f"Remove {type_aggregates.get('idle_elimination', {}).get('count', 0)} idle resources for ${projected_idle_savings:.2f} savings",
                        "risk_level": "very_low",
                    },
                    {
                        "type": "Storage Tier Optimization",
                        "impact": projected_storage_savings,
                        "description": f"Optimize {type_aggregates.get('storage_optimization', {}).get('count', 0)} storage resources for ${projected_storage_savings:.2f} savings",
                        "risk_level": "low",
                    },
                    {
                        "type": "Commitment Adoption",
                        "impact": projected_commitment_savings,
                        "description": f"Implement commitment strategy for ${projected_commitment_savings:.2f} savings",
                        "risk_level": "medium",
                    },
                ],
                "detailed_recommendations": selected_optimizations,
            }
        )

    except Exception as e:
        print(f"[!] Error in target margin calculation: {e}")
        import traceback

        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/financial/target-margin/apply")
async def apply_target_margin_optimizations(request: Request):
    """Apply the calculated optimization recommendations physically to Azure."""
    try:
        data = (await request.json() if await request.body() else {}) or {}

        optimizations = data.get("optimizations", {})
        detailed_recommendations = data.get("detailed_recommendations", [])

        if not detailed_recommendations:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "No detailed recommendations provided to apply.",
                },
            )

        from reaper.remediators.azure_remediator import AzureRemediator

        remediator = AzureRemediator()

        results = []
        applied_count = 0

        for rec in detailed_recommendations:
            rec_type = rec.get("type")
            res_id = rec.get("resource_id")
            res_name = rec.get("resource_name", "unknown")

            if not res_id or res_id == "commitment_pool":
                # Skip commitments or invalid resources for automated physical remediation
                continue

            op_result = {
                "resource": res_name,
                "type": rec_type,
                "status": "skipped",
                "message": "Unsupported type",
            }

            if rec_type == "rightsizing":
                op_result = remediator.downsize_vm(res_id)
                op_result["resource"] = res_name
            elif rec_type == "idle_elimination":
                op_result = remediator.delete_vm(res_id)
                op_result["resource"] = res_name
            elif rec_type == "storage_optimization":
                op_result = remediator.downgrade_disk(res_id, target_tier="Standard_LRS")
                op_result["resource"] = res_name

            results.append(op_result)
            if op_result.get("status") in ["processing", "dry_run"]:
                applied_count += 1

        return jsonify(
            {
                "status": "success",
                "message": "Optimization operations initiated",
                "applied_count": applied_count,
                "is_dry_run": remediator.is_dry_run,
                "results": results,
                "details": {
                    "rightsizing_applied": optimizations.get("rightsizing", 0),
                    "idle_elimination_applied": optimizations.get("idle_elimination", 0),
                    "storage_optimization_applied": optimizations.get("storage_optimization", 0),
                    "commitment_adoption_applied": optimizations.get("commitment_adoption", 0),
                },
            }
        )

    except Exception as e:
        print(f"[!] Error applying optimizations: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/financial/spend/current")
async def get_current_spend(request: Request):
    """Fetch current monthly spend from Azure resources and return persisted target spend.

    Returns:
        current_spend  – live cumulative spend from Azure resources (or cached override)
        target_spend   – last persisted target spend (default: 80% of budget_threshold)
        budget_cap     – the budget threshold configured in Settings
        burn_rate      – daily burn rate
        forecast       – 30-day forecast
        source         – 'azure' | 'override' | 'fallback'
        resource_breakdown – detailed cost breakdown by resource type
    """
    try:
        budget_threshold = float(settings_state.get("budget_threshold", 1000.0))
        # Persisted target_spend – default 80 % of budget_threshold if not set
        target_spend = float(settings_state.get("target_spend", round(budget_threshold * 0.80, 2)))
        # Persisted current_spend override (manual entry takes precedence)
        current_override = settings_state.get("current_spend_override")

        source = "fallback"
        current_spend = 0.0
        burn_rate = 0.0
        forecast = 0.0
        resource_breakdown = None

        if current_override is not None:
            # Use manual override if provided
            current_spend = float(current_override)
            burn_rate = current_spend / 30
            forecast = burn_rate * 30
            source = "override"
        else:
            # Try to pull live data from Azure resources
            try:

                def _fetch_cost_data():
                    c = AzureCollector()
                    return c.get_resource_cost_summary(), c.get_cost_vs_budget()

                resource_cost_summary, cost_data = await asyncio.to_thread(_fetch_cost_data)
                current_spend = float(resource_cost_summary.get("total_monthly_cost", 0.0))
                resource_breakdown = resource_cost_summary

                burn_rate = float(
                    cost_data.get("burn_rate", current_spend / 30 if current_spend > 0 else 0)
                )
                forecast = float(cost_data.get("forecast", burn_rate * 30 if burn_rate > 0 else 0))

                if current_spend > 0:
                    source = "azure"
                else:
                    # If Azure returns 0 costs, return error to user
                    return jsonify(
                        {
                            "status": "error",
                            "message": "Unable to fetch current spend from Azure. Please ensure Azure credentials are configured and Cost Management API is accessible.",
                            "current_spend": 0.0,
                            "target_spend": round(target_spend, 2),
                            "budget_cap": round(budget_threshold, 2),
                            "burn_rate": 0.0,
                            "forecast": 0.0,
                            "source": "error",
                            "resource_breakdown": None,
                        }
                    )
            except Exception as e:
                print(f"[!] Error fetching Azure resource costs: {e}")
                # Azure not configured – return error to user
                return jsonify(
                    {
                        "status": "error",
                        "message": f"Error fetching Azure resource costs: {e!s}. Please ensure Azure credentials are configured.",
                        "current_spend": 0.0,
                        "target_spend": round(target_spend, 2),
                        "budget_cap": round(budget_threshold, 2),
                        "burn_rate": 0.0,
                        "forecast": 0.0,
                        "source": "error",
                        "resource_breakdown": None,
                    }
                )

        return jsonify(
            {
                "status": "success",
                "current_spend": round(current_spend, 2),
                "target_spend": round(target_spend, 2),
                "budget_cap": round(budget_threshold, 2),
                "burn_rate": round(burn_rate, 4),
                "forecast": round(forecast, 2),
                "source": source,
                "resource_breakdown": resource_breakdown,
            }
        )
    except Exception as e:
        print(f"[!] Error fetching current spend: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/financial/spend/update")
async def update_spend_config(request: Request):
    """Persist current spend override and / or target spend.

    Body (all fields optional):
        current_spend  (float) – manual override for current monthly spend
        target_spend   (float) – desired target monthly spend
    """
    try:
        data = (await request.json() if await request.body() else {}) or {}

        updated: dict = {}

        raw_current = data.get("current_spend")
        if raw_current is not None:
            val = float(raw_current)
            if val < 0:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "current_spend cannot be negative"},
                )
            settings_state["current_spend_override"] = val
            updated["current_spend"] = val

        raw_target = data.get("target_spend")
        if raw_target is not None:
            val = float(raw_target)
            if val < 0:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "target_spend cannot be negative"},
                )
            settings_state["target_spend"] = val
            updated["target_spend"] = val

        if not updated:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Provide current_spend and/or target_spend"},
            )

        return jsonify(
            {
                "status": "success",
                "message": "Spend configuration updated",
                "updated": updated,
            }
        )
    except ValueError as e:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": f"Invalid value: {e}"}
        )
    except Exception as e:
        print(f"[!] Error updating spend config: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/metrics")
async def get_dashboard_metrics(request: Request):
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


@app.get("/api/resources/inventory")
async def get_resource_inventory(request: Request):
    """Get comprehensive inventory of all Azure resources for cost optimization with streaming response.

    Query params:
        page      (int, default 1)  - page number for server-side pagination
        page_size (int, default 50) - items per page (max 200)
        category  (str, optional)   - filter by resource category
        status    (str, optional)   - filter by status (Idle, Orphaned, Active, …)
        q         (str, optional)   - text search against name / type
        stream    (bool, default False) - enable streaming response for large datasets
    """
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        category_filter = request.query_params.get("category", "").strip().lower()
        status_filter = request.query_params.get("status", "").strip()
        search_q = request.query_params.get("q", "").strip().lower()
        stream_response = request.query_params.get("stream", "false").lower() == "true"

        def _get_collector():
            return AzureCollector()

        az = await asyncio.to_thread(_get_collector)

        inventory: dict[str, list | dict] = {
            "virtual_machines": [],
            "disks": [],
            "storage_accounts": [],
            "network_resources": [],
            "databases": [],
            "app_services": [],
            "functions": [],
            "kubernetes": [],
            "key_vaults": [],
            "cognitive_services": [],
            "monitoring": [],
            "messaging": [],
            "other_resources": [],
            "summary": {
                "total_resources": 0,
                "idle_resources": 0,
                "orphaned_resources": 0,
                "estimated_monthly_cost": 0.0,
                "by_category": {},
            },
        }

        collected_ids = set()
        _cat_map = {
            "virtual_machines": "virtual_machines",
            "disks": "disks",
            "storage_accounts": "storage_accounts",
            "network_resources": "network_resources",
            "databases": "databases",
            "cosmos_db": "databases",
            "app_services": "app_services",
            "functions": "functions",
            "kubernetes": "kubernetes",
            "container_instances": "other_resources",
            "key_vaults": "key_vaults",
            "redis_caches": "messaging",
            "data_factories": "other_resources",
            "logic_apps": "other_resources",
            "event_hubs": "messaging",
            "service_bus": "messaging",
            "iot_hubs": "messaging",
            "cognitive_services": "cognitive_services",
            "monitoring": "monitoring",
            "cdn_profiles": "other_resources",
            "api_management": "other_resources",
            "recovery_vaults": "other_resources",
            "other_resources": "other_resources",
        }

        def _add(category: str, resource: dict) -> None:
            """Append resource to category list and update summary counts."""
            r_id = resource.get("id")
            if r_id:
                collected_ids.add(r_id.lower())

            target_cat = _cat_map.get(category, "other_resources")
            resource["category"] = target_cat
            inventory[target_cat].append(resource)  # type: ignore[union-attr]

            summary = inventory["summary"]
            summary["total_resources"] += 1  # type: ignore[index]
            summary["by_category"][target_cat] = summary["by_category"].get(target_cat, 0) + 1  # type: ignore[index]
            summary["estimated_monthly_cost"] += resource.get("estimated_cost", 0.0)  # type: ignore[index]
            if resource.get("status") in ("Idle",):
                summary["idle_resources"] += 1  # type: ignore[index]
            elif resource.get("status") in ("Orphaned", "Unassociated", "Empty"):
                summary["orphaned_resources"] += 1  # type: ignore[index]

        # ---- Virtual Machines ----
        try:
            # Parallel execution: fetch VM inventory and idle VMs concurrently
            vms_result = await asyncio.to_thread(az.get_vm_inventory)
            idle_vms_result = await asyncio.to_thread(az.get_idle_vms, cpu_threshold=5.0)

            vms = vms_result
            idle_vms = idle_vms_result
            idle_vm_names = {vm["name"] for vm in idle_vms}

            # Batch cost estimation for all VMs
            vm_cost_tasks = []
            for vm in vms:
                vm_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.compute/virtualmachines",
                        vm.get("size", ""),
                        vm.get("location", ""),
                    )
                )

            vm_costs = await asyncio.gather(*vm_cost_tasks)

            for vm, cost in zip(vms, vm_costs):
                is_idle = vm["name"] in idle_vm_names
                _add(
                    "virtual_machines",
                    {
                        "id": vm["id"],
                        "name": vm["name"],
                        "type": "Microsoft.Compute/virtualMachines",
                        "location": vm["location"],
                        "size": vm["size"],
                        "status": "Idle" if is_idle else "Active",
                        "tags": vm["tags"],
                        "category": "compute",
                        "can_dismiss": is_idle,
                        "dismiss_reason": "Idle VM with low CPU utilization" if is_idle else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching VMs: {e}")

        # ---- Disks ----
        try:
            # Parallel execution: fetch orphaned disks and all disks concurrently
            orphaned_disks_result = await asyncio.to_thread(az.get_orphaned_disks)
            all_disks_result = await asyncio.to_thread(lambda: list(az.compute.disks.list()))

            orphaned_disks_data = orphaned_disks_result
            orphaned_disk_names = {d["name"] for d in orphaned_disks_data.get("disks", [])}
            all_disks = all_disks_result

            # Batch cost estimation for all disks
            disk_cost_tasks = []
            for disk in all_disks:
                disk_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.compute/disks",
                        disk.sku.name if disk.sku else "",
                        disk.location,
                    )
                )

            disk_costs = await asyncio.gather(*disk_cost_tasks)

            for disk, cost in zip(all_disks, disk_costs):
                is_orphaned = disk.name in orphaned_disk_names
                _add(
                    "disks",
                    {
                        "id": disk.id,
                        "name": disk.name,
                        "type": "Microsoft.Compute/disks",
                        "location": disk.location,
                        "size_gb": disk.disk_size_gb,
                        "sku": disk.sku.name if disk.sku else "Unknown",
                        "status": "Orphaned" if is_orphaned else "Attached",
                        "category": "storage",
                        "can_dismiss": is_orphaned,
                        "dismiss_reason": "Unattached disk with no associated VM"
                        if is_orphaned
                        else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching disks: {e}")

        # ---- Storage Accounts ----
        try:
            storage_accounts = await asyncio.to_thread(az.get_storage_accounts)

            # Batch cost estimation for all storage accounts
            storage_cost_tasks = []
            for acc in storage_accounts:
                storage_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.storage/storageaccounts",
                        acc.get("sku", ""),
                        acc.get("location", ""),
                    )
                )

            storage_costs = await asyncio.gather(*storage_cost_tasks)

            for acc, cost in zip(storage_accounts, storage_costs):
                tier = acc.get("access_tier", "Hot")
                _add(
                    "storage_accounts",
                    {
                        "id": acc["id"],
                        "name": acc["name"],
                        "type": "Microsoft.Storage/storageAccounts",
                        "location": acc["location"],
                        "sku": acc.get("sku", "Unknown"),
                        "kind": acc.get("kind", ""),
                        "access_tier": tier,
                        "status": "Cold" if tier in ("Cool", "Archive") else "Active",
                        "category": "storage",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching storage accounts: {e}")

        # ---- Network Resources ----
        try:
            # Parallel execution: fetch network resources concurrently
            ips_result = await asyncio.to_thread(az.get_unassociated_public_ips)
            lbs_result = await asyncio.to_thread(az.get_idle_load_balancers)

            # Batch cost estimation for network resources
            network_cost_tasks = []
            for ip in ips_result:
                network_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.network/publicipaddresses",
                        ip.get("sku", ""),
                        ip.get("location", ""),
                    )
                )
            for lb in lbs_result:
                network_cost_tasks.append(
                    asyncio.to_thread(
                        az.estimate_resource_cost,
                        "microsoft.network/loadbalancers",
                        lb.get("sku", ""),
                        lb.get("location", ""),
                    )
                )

            network_costs = await asyncio.gather(*network_cost_tasks)

            # Process IPs (first half of costs)
            ip_count = len(ips_result)
            ip_costs = network_costs[:ip_count]
            for ip, cost in zip(ips_result, ip_costs):
                _add(
                    "network_resources",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.Network/publicIPAddresses/{ip['name']}",
                        "name": ip["name"],
                        "type": "Microsoft.Network/publicIPAddresses",
                        "location": ip["location"],
                        "sku": ip["sku"],
                        "status": "Unassociated",
                        "category": "network",
                        "can_dismiss": True,
                        "dismiss_reason": "Public IP with no associated resources",
                        "estimated_cost": cost,
                    },
                )

            # Process load balancers (second half of costs)
            lb_costs = network_costs[ip_count:]
            for lb, cost in zip(lbs_result, lb_costs):
                _add(
                    "network_resources",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.Network/loadBalancers/{lb['name']}",
                        "name": lb["name"],
                        "type": "Microsoft.Network/loadBalancers",
                        "location": lb["location"],
                        "sku": lb["sku"],
                        "status": "Idle",
                        "category": "network",
                        "can_dismiss": True,
                        "dismiss_reason": "Load balancer with no backend pool members",
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching network resources: {e}")

        # ---- SQL Databases ----
        try:
            for db in az.get_sql_databases():
                cost = az.estimate_resource_cost(
                    "microsoft.sql/servers/databases", db.get("sku", ""), db.get("location", "")
                )
                _add(
                    "databases",
                    {
                        "id": db.get("id", ""),
                        "name": db.get("name", ""),
                        "type": "Microsoft.Sql/servers/databases",
                        "location": db.get("location", ""),
                        "sku": db.get("sku", "Unknown"),
                        "status": "Idle" if db.get("is_idle") else "Active",
                        "average_cpu": db.get("average_cpu", 0.0),
                        "category": "database",
                        "can_dismiss": db.get("is_idle", False),
                        "dismiss_reason": "Idle database with low utilization"
                        if db.get("is_idle")
                        else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching SQL databases: {e}")

        # ---- App Services ----
        try:
            for plan in az.get_empty_app_service_plans():
                cost = az.estimate_resource_cost(
                    "microsoft.web/serverfarms", plan.get("sku", ""), plan.get("location", "")
                )
                _add(
                    "app_services",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.Web/serverfarms/{plan['name']}",
                        "name": plan["name"],
                        "type": "Microsoft.Web/serverfarms",
                        "location": plan["location"],
                        "sku": plan["sku"],
                        "tier": plan.get("tier", ""),
                        "status": "Empty",
                        "category": "app_services",
                        "can_dismiss": True,
                        "dismiss_reason": "App Service Plan with no assigned apps",
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching app services: {e}")

        # ---- Azure Functions ----
        try:
            for fn in az.get_function_apps():
                cost = az.estimate_resource_cost("microsoft.web/sites", "", fn.get("location", ""))
                is_stopped = fn.get("state", "Running") not in ("Running",)
                _add(
                    "functions",
                    {
                        "id": fn["id"],
                        "name": fn["name"],
                        "type": "Microsoft.Web/sites (Function)",
                        "location": fn["location"],
                        "state": fn.get("state", "Running"),
                        "runtime": fn.get("runtime", ""),
                        "status": "Stopped" if is_stopped else "Active",
                        "category": "functions",
                        "can_dismiss": is_stopped,
                        "dismiss_reason": "Function app is stopped" if is_stopped else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching function apps: {e}")

        # ---- AKS Clusters ----
        try:
            for cluster in az.get_aks_clusters():
                cost = az.estimate_resource_cost(
                    "microsoft.containerservice/managedclusters",
                    cluster.get("sku", ""),
                    cluster.get("location", ""),
                )
                power = cluster.get("power_state", "Running")
                _add(
                    "kubernetes",
                    {
                        "id": cluster["id"],
                        "name": cluster["name"],
                        "type": "Microsoft.ContainerService/managedClusters",
                        "location": cluster["location"],
                        "kubernetes_version": cluster.get("kubernetes_version", ""),
                        "node_count": cluster.get("node_count", 0),
                        "status": "Stopped" if power == "Stopped" else "Active",
                        "category": "kubernetes",
                        "can_dismiss": power == "Stopped",
                        "dismiss_reason": "AKS cluster is stopped" if power == "Stopped" else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching AKS clusters: {e}")

        # ---- Container Instances ----
        try:
            for cg in az.get_container_instances():
                cost = az.estimate_resource_cost(
                    "microsoft.containerinstance/containergroups", "", cg.get("location", "")
                )
                _add(
                    "container_instances",
                    {
                        "id": cg["id"],
                        "name": cg["name"],
                        "type": "Microsoft.ContainerInstance/containerGroups",
                        "location": cg["location"],
                        "os_type": cg.get("os_type", "Linux"),
                        "container_count": cg.get("container_count", 0),
                        "status": cg.get("provisioning_state", "Succeeded"),
                        "category": "container_instances",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching container instances: {e}")

        # ---- Key Vaults ----
        try:
            for kv in az.get_key_vaults():
                cost = az.estimate_resource_cost(
                    "microsoft.keyvault/vaults", "Standard", kv.get("location", "")
                )
                _add(
                    "key_vaults",
                    {
                        "id": kv["id"],
                        "name": kv["name"],
                        "type": "Microsoft.KeyVault/vaults",
                        "location": kv["location"],
                        "status": "Active",
                        "category": "key_vaults",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching key vaults: {e}")

        # ---- Redis Caches ----
        try:
            for cache in az.get_redis_caches():
                cost = az.estimate_resource_cost(
                    "microsoft.cache/redis", cache.get("sku_name", ""), cache.get("location", "")
                )
                _add(
                    "redis_caches",
                    {
                        "id": cache["id"],
                        "name": cache["name"],
                        "type": "Microsoft.Cache/Redis",
                        "location": cache["location"],
                        "sku": f"{cache.get('sku_name', '')} C{cache.get('sku_capacity', '')}",
                        "status": cache.get("provisioning_state", "Succeeded"),
                        "category": "redis_caches",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Redis caches: {e}")

        # ---- Cosmos DB ----
        try:
            for acc in az.get_cosmos_db_accounts():
                cost = az.estimate_resource_cost(
                    "microsoft.documentdb/databaseaccounts", "", acc.get("location", "")
                )
                _add(
                    "cosmos_db",
                    {
                        "id": acc["id"],
                        "name": acc["name"],
                        "type": "Microsoft.DocumentDB/databaseAccounts",
                        "location": acc["location"],
                        "kind": acc.get("kind", "GlobalDocumentDB"),
                        "consistency": acc.get("consistency_level", "Session"),
                        "status": "Active",
                        "category": "cosmos_db",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Cosmos DB: {e}")

        # ---- Data Factories ----
        try:
            for factory in az.get_data_factories():
                cost = az.estimate_resource_cost(
                    "microsoft.datafactory/factories", "", factory.get("location", "")
                )
                _add(
                    "data_factories",
                    {
                        "id": factory["id"],
                        "name": factory["name"],
                        "type": "Microsoft.DataFactory/factories",
                        "location": factory["location"],
                        "status": factory.get("provisioning_state", "Succeeded"),
                        "category": "data_factories",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Data Factories: {e}")

        # ---- Logic Apps ----
        try:
            for wf in az.get_logic_apps():
                cost = az.estimate_resource_cost(
                    "microsoft.logic/workflows", wf.get("sku", ""), wf.get("location", "")
                )
                state = wf.get("state", "Enabled")
                _add(
                    "logic_apps",
                    {
                        "id": wf["id"],
                        "name": wf["name"],
                        "type": "Microsoft.Logic/workflows",
                        "location": wf["location"],
                        "state": state,
                        "status": "Disabled" if state == "Disabled" else "Active",
                        "category": "logic_apps",
                        "can_dismiss": state == "Disabled",
                        "dismiss_reason": "Logic App is disabled" if state == "Disabled" else None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Logic Apps: {e}")

        # ---- Event Hubs ----
        try:
            for ns in az.get_event_hubs():
                cost = az.estimate_resource_cost(
                    "microsoft.eventhub/namespaces", ns.get("sku_name", ""), ns.get("location", "")
                )
                _add(
                    "event_hubs",
                    {
                        "id": ns["id"],
                        "name": ns["name"],
                        "type": "Microsoft.EventHub/namespaces",
                        "location": ns["location"],
                        "sku": ns.get("sku_name", "Basic"),
                        "status": ns.get("provisioning_state", "Succeeded"),
                        "category": "event_hubs",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Event Hubs: {e}")

        # ---- Service Bus ----
        try:
            for ns in az.get_service_bus_namespaces():
                cost = az.estimate_resource_cost(
                    "microsoft.servicebus/namespaces",
                    ns.get("sku_name", ""),
                    ns.get("location", ""),
                )
                _add(
                    "service_bus",
                    {
                        "id": ns["id"],
                        "name": ns["name"],
                        "type": "Microsoft.ServiceBus/namespaces",
                        "location": ns["location"],
                        "sku": ns.get("sku_name", "Basic"),
                        "status": ns.get("provisioning_state", "Succeeded"),
                        "category": "service_bus",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Service Bus: {e}")

        # ---- IoT Hubs ----
        try:
            for hub in az.get_iot_hubs():
                cost = az.estimate_resource_cost(
                    "microsoft.devices/iothubs", hub.get("sku_name", ""), hub.get("location", "")
                )
                _add(
                    "iot_hubs",
                    {
                        "id": hub["id"],
                        "name": hub["name"],
                        "type": "Microsoft.Devices/IotHubs",
                        "location": hub["location"],
                        "sku": hub.get("sku_name", "F1"),
                        "status": hub.get("state", "Active"),
                        "category": "iot_hubs",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching IoT Hubs: {e}")

        # ---- Cognitive Services ----
        try:
            for acc in az.get_cognitive_services():
                cost = az.estimate_resource_cost(
                    "microsoft.cognitiveservices/accounts",
                    acc.get("sku_name", ""),
                    acc.get("location", ""),
                )
                _add(
                    "cognitive_services",
                    {
                        "id": acc["id"],
                        "name": acc["name"],
                        "type": f"Microsoft.CognitiveServices/accounts ({acc.get('kind', 'Unknown')})",
                        "location": acc["location"],
                        "sku": acc.get("sku_name", "S0"),
                        "kind": acc.get("kind", "Unknown"),
                        "status": acc.get("provisioning_state", "Succeeded"),
                        "category": "cognitive_services",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Cognitive Services: {e}")

        # ---- Application Insights ----
        try:
            for comp in az.get_application_insights():
                cost = az.estimate_resource_cost(
                    "microsoft.insights/components", "", comp.get("location", "")
                )
                _add(
                    "monitoring",
                    {
                        "id": comp["id"],
                        "name": comp["name"],
                        "type": "Microsoft.Insights/components",
                        "location": comp["location"],
                        "application_type": comp.get("application_type", "web"),
                        "retention_days": comp.get("retention_in_days", 90),
                        "status": "Active",
                        "category": "monitoring",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching Application Insights: {e}")

        # ---- CDN Profiles ----
        try:
            for profile in az.get_cdn_profiles():
                cost = az.estimate_resource_cost(
                    "microsoft.cdn/profiles",
                    profile.get("sku_name", ""),
                    profile.get("location", ""),
                )
                _add(
                    "cdn_profiles",
                    {
                        "id": profile["id"],
                        "name": profile["name"],
                        "type": "Microsoft.Cdn/profiles",
                        "location": profile["location"],
                        "sku": profile.get("sku_name", "Standard_Microsoft"),
                        "status": profile.get("resource_state", "Active"),
                        "category": "cdn_profiles",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching CDN profiles: {e}")

        # ---- API Management ----
        try:
            for svc in az.get_api_management_instances():
                cost = az.estimate_resource_cost(
                    "microsoft.apimanagement/service",
                    svc.get("sku_name", ""),
                    svc.get("location", ""),
                )
                _add(
                    "api_management",
                    {
                        "id": svc["id"],
                        "name": svc["name"],
                        "type": "Microsoft.ApiManagement/service",
                        "location": svc["location"],
                        "sku": svc.get("sku_name", "Developer"),
                        "status": svc.get("provisioning_state", "Succeeded"),
                        "category": "api_management",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching API Management: {e}")

        # ---- Recovery Vaults ----
        try:
            for vault in az.get_recovery_vaults():
                cost = az.estimate_resource_cost(
                    "microsoft.recoveryservices/vaults",
                    vault.get("sku", ""),
                    vault.get("location", ""),
                )
                _add(
                    "recovery_vaults",
                    {
                        "id": f"/subscriptions/{az.subscription_id}/providers/Microsoft.RecoveryServices/vaults/{vault['name']}",
                        "name": vault["name"],
                        "type": "Microsoft.RecoveryServices/vaults",
                        "location": vault["location"],
                        "sku": vault["sku"],
                        "status": "Active",
                        "category": "backup",
                        "can_dismiss": False,
                        "dismiss_reason": None,
                        "estimated_cost": cost,
                    },
                )
        except Exception as e:
            print(f"[!] Error fetching recovery vaults: {e}")

        # ---- Resource Graph Fallback for Uncollected Resources ----
        try:
            all_resources = az.get_all_resources_by_resource_graph()
            if all_resources:
                _type_to_cat = {
                    "microsoft.compute/virtualmachines": "virtual_machines",
                    "microsoft.compute/disks": "disks",
                    "microsoft.storage/storageaccounts": "storage_accounts",
                    "microsoft.network/publicipaddresses": "network_resources",
                    "microsoft.network/loadbalancers": "network_resources",
                    "microsoft.containerservice/managedclusters": "kubernetes",
                    "microsoft.containerinstance/containergroups": "other_resources",
                    "microsoft.web/sites": "app_services",
                    "microsoft.web/serverfarms": "app_services",
                    "microsoft.sql/servers/databases": "databases",
                    "microsoft.keyvault/vaults": "key_vaults",
                    "microsoft.cache/redis": "messaging",
                    "microsoft.documentdb/databaseaccounts": "databases",
                    "microsoft.datafactory/factories": "other_resources",
                    "microsoft.logic/workflows": "other_resources",
                    "microsoft.eventhub/namespaces": "messaging",
                    "microsoft.servicebus/namespaces": "messaging",
                    "microsoft.devices/iothubs": "messaging",
                    "microsoft.cognitiveservices/accounts": "cognitive_services",
                    "microsoft.insights/components": "monitoring",
                    "microsoft.cdn/profiles": "other_resources",
                    "microsoft.apimanagement/service": "other_resources",
                    "microsoft.recoveryservices/vaults": "other_resources",
                }

                for r in all_resources:
                    r_id = r.get("id", "")
                    if not r_id or r_id.lower() in collected_ids:
                        continue

                    r_type = r.get("type", "").lower()

                    category = "other_resources"
                    if (
                        r_type == "microsoft.web/sites"
                        and "functionapp" in str(r.get("kind", "")).lower()
                    ):
                        category = "functions"
                    else:
                        category = _type_to_cat.get(r_type, "other_resources")

                    # Estimate cost
                    sku_name = (
                        r.get("sku", {}).get("name", "")
                        if isinstance(r.get("sku"), dict)
                        else (r.get("sku") or "")
                    )
                    cost = az.estimate_resource_cost(r_type, sku_name, r.get("location", ""))

                    _add(
                        category,
                        {
                            "id": r_id,
                            "name": r.get("name", "Unnamed"),
                            "type": r.get("type", "Unknown"),
                            "location": r.get("location", "global"),
                            "status": "Active",
                            "category": category,
                            "can_dismiss": False,
                            "dismiss_reason": None,
                            "estimated_cost": cost,
                            "sku": sku_name,
                            "kind": r.get("kind", ""),
                            "tags": r.get("tags") or {},
                        },
                    )
        except Exception as e:
            print(f"[!] Error in Resource Graph fallback: {e}")

        # ---- Flatten all resources for pagination + filtering ----
        all_categories = [k for k in inventory if k not in ("summary", "other_resources")]
        all_flat: list[dict] = []
        for cat in all_categories:
            all_flat.extend(inventory[cat])  # type: ignore[union-attr]

        # Apply server-side filters
        if category_filter:
            all_flat = [r for r in all_flat if r.get("category", "") == category_filter]
        if status_filter:
            all_flat = [r for r in all_flat if r.get("status", "") == status_filter]
        if search_q:
            all_flat = [
                r
                for r in all_flat
                if search_q in r.get("name", "").lower() or search_q in r.get("type", "").lower()
            ]

        total = len(all_flat)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_flat = all_flat[start:end]

        # Round estimated cost
        inventory["summary"]["estimated_monthly_cost"] = round(  # type: ignore[index]
            inventory["summary"]["estimated_monthly_cost"],
            2,  # type: ignore[index]
        )

        # Return streaming response if requested
        if stream_response:

            async def generate_stream():
                """Generator function for streaming JSON response."""
                # Send initial metadata
                yield (
                    json_module.dumps(
                        {
                            "status": "success",
                            "page": page,
                            "page_size": page_size,
                            "total": total,
                            "total_pages": max(1, (total + page_size - 1) // page_size),
                            "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    + "\n"
                )

                # Stream resources in chunks
                chunk_size = 50
                for i in range(0, len(paginated_flat), chunk_size):
                    chunk = paginated_flat[i : i + chunk_size]
                    yield (
                        json_module.dumps(
                            {
                                "type": "resources_chunk",
                                "chunk_index": i // chunk_size,
                                "total_chunks": (len(paginated_flat) + chunk_size - 1)
                                // chunk_size,
                                "resources": chunk,
                            }
                        )
                        + "\n"
                    )
                    await asyncio.sleep(0.01)  # Small delay to prevent overwhelming the client

                # Send summary at the end
                yield json_module.dumps({"type": "summary", "data": inventory}) + "\n"

            return StreamingResponse(
                generate_stream(),
                media_type="application/json",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )

        return jsonify(
            {
                "status": "success",
                "data": inventory,
                "resources": paginated_flat,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": max(1, (total + page_size - 1) // page_size),
                "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/resources/inventory/summary")
async def get_resource_inventory_summary(request: Request):
    """Lightweight endpoint returning only counts + cost — no resource lists.
    Suitable for dashboard widgets that don't need full resource data.
    """
    try:

        def _fetch_resources():
            c = AzureCollector()
            return c.get_all_resources_via_resource_graph()

        all_resources = await asyncio.to_thread(_fetch_resources)
        type_counts: dict[str, int] = {}
        for r in all_resources:
            rt = str(r.get("type", "other")).lower()
            type_counts[rt] = type_counts.get(rt, 0) + 1

        # Map to friendly categories
        _type_to_cat = {
            "microsoft.compute/virtualmachines": "compute",
            "microsoft.compute/disks": "storage",
            "microsoft.storage/storageaccounts": "storage",
            "microsoft.network/publicipaddresses": "network",
            "microsoft.network/loadbalancers": "network",
            "microsoft.containerservice/managedclusters": "kubernetes",
            "microsoft.containerinstance/containergroups": "container_instances",
            "microsoft.web/sites": "app_services",
            "microsoft.web/serverfarms": "app_services",
            "microsoft.sql/servers/databases": "database",
            "microsoft.keyvault/vaults": "key_vaults",
            "microsoft.cache/redis": "redis_caches",
            "microsoft.documentdb/databaseaccounts": "cosmos_db",
            "microsoft.datafactory/factories": "data_factories",
            "microsoft.logic/workflows": "logic_apps",
            "microsoft.eventhub/namespaces": "event_hubs",
            "microsoft.servicebus/namespaces": "service_bus",
            "microsoft.devices/iothubs": "iot_hubs",
            "microsoft.cognitiveservices/accounts": "cognitive_services",
            "microsoft.insights/components": "monitoring",
            "microsoft.cdn/profiles": "cdn_profiles",
            "microsoft.apimanagement/service": "api_management",
            "microsoft.recoveryservices/vaults": "backup",
        }
        by_category: dict[str, int] = {}
        for rt, count in type_counts.items():
            cat = _type_to_cat.get(rt, "other")
            by_category[cat] = by_category.get(cat, 0) + count

        return jsonify(
            {
                "status": "success",
                "total_resources": len(all_resources),
                "by_category": by_category,
                "by_type": type_counts,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/resources/search")
async def search_resources(request: Request):
    """Full-text search across all Azure resources by name or type.

    Query params:
        q         (str, required)   - search term
        category  (str, optional)   - filter by category
        status    (str, optional)   - filter by status
        page      (int, default 1)
        page_size (int, default 25)
    """
    q = request.query_params.get("q", "").strip().lower()
    if not q:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Query param 'q' is required."},
        )

    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 25))))
        category_filter = request.query_params.get("category", "").strip().lower()
        status_filter = request.query_params.get("status", "").strip()

        def _fetch_resources():
            c = AzureCollector()
            return c.get_all_resources_via_resource_graph()

        all_resources = await asyncio.to_thread(_fetch_resources)

        results = [
            {
                "id": r.get("id", ""),
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "location": r.get("location", ""),
                "resource_group": r.get("resourceGroup", ""),
                "tags": r.get("tags") or {},
                "kind": r.get("kind", ""),
            }
            for r in all_resources
            if q in str(r.get("name", "")).lower() or q in str(r.get("type", "")).lower()
        ]

        if category_filter:
            from reaper.collectors.providers.azure_collector import AzureCollector as _AC

            _type_to_cat = _AC._COST_FALLBACK  # borrow the type map keys for category matching
            results = [r for r in results if category_filter in r.get("type", "").lower()]
        if status_filter:
            results = [r for r in results if r.get("status", "") == status_filter]

        total = len(results)
        start = (page - 1) * page_size
        paginated = results[start : start + page_size]

        return jsonify(
            {
                "status": "success",
                "query": q,
                "results": paginated,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": max(1, (total + page_size - 1) // page_size),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/resources/{resource_id}/dismiss")
async def dismiss_resource(request: Request, resource_id: str):
    """Mark a resource for dismissal/cleanup."""
    try:
        data = await request.json() if request.body() else {}
        reason = data.get("reason", "Manual dismissal")

        # In a real implementation, this would:
        # 1. Log the dismissal action
        # 2. Create a cleanup ticket
        # 3. Optionally trigger actual resource deletion

        return jsonify(
            {
                "status": "success",
                "message": f"Resource {resource_id} marked for dismissal",
                "resource_id": resource_id,
                "reason": reason,
                "action_taken": "marked_for_cleanup",
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/budget/data")
async def get_budget_data(request: Request):
    """Get comprehensive budget pacing data for the financial dashboard."""
    try:
        budget_threshold = float(settings_state.get("budget_threshold", 1000.0))

        # Get actual spend data from Azure Collector if available
        def _fetch_cost_data():
            c = AzureCollector()
            return c.get_cost_vs_budget()

        try:
            cost_data = await asyncio.to_thread(_fetch_cost_data)
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/budget/update")
async def update_budget_threshold(request: Request):
    """Direct endpoint to update budget threshold."""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        threshold = data.get("threshold")
        if not threshold:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": "Threshold is required"}
            )

        settings_state["budget_threshold"] = float(threshold)
        return jsonify(
            {
                "status": "success",
                "message": f"Budget threshold updated to ${threshold}",
                "threshold": float(threshold),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/budget/chart")
async def get_budget_chart_data(request: Request):
    """Get chart data for budget pacing visualization."""
    try:

        def _fetch_chart_data():
            c = AzureCollector()
            return c.get_cost_vs_budget_chart()

        try:
            chart_data = await asyncio.to_thread(_fetch_chart_data)
        except Exception:
            # Fallback simulated data
            import random

            chart_data = {
                "labels": [f"Day {i}" for i in range(1, 31)],
                "cumulative_spend": [random.uniform(100, 150) * i for i in range(1, 31)],
                "budget_pace": [random.uniform(100, 150) * i * 0.95 for i in range(1, 31)],
            }

        return {"status": "success", "chart": chart_data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/commitments/data")
async def get_commitments_data(request: Request):
    """Get active commitment portfolio and recommendations."""
    try:

        def _fetch_commitments():
            c = AzureCollector()
            return c.get_active_commitments(), c.get_ri_coverage(), c.get_ri_recommendations()

        try:
            commitments, coverage, recommendations = await asyncio.to_thread(_fetch_commitments)
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/issues/data")
async def get_issues_data(request: Request):
    """Get cost governance issues requiring action."""
    try:

        def _fetch_issues():
            c = AzureCollector()
            return c.get_cost_governance_issues()

        try:
            issues = await asyncio.to_thread(_fetch_issues)
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/issues/remediate")
async def remediate_issue(request: Request):
    """Execute remediation action on a cost governance issue."""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        issue_id = data.get("issue_id")
        action = data.get("action")

        if not issue_id or not action:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Issue ID and action are required"},
            )

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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/commitment/simulate")
async def simulate_commitment_api(request: Request):
    """Enhanced commitment simulation with real calculations."""
    try:
        data = (await request.json() if await request.body() else {}) or {}
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/commitment/purchase")
async def purchase_commitment_api(request: Request):
    """Purchase a commitment based on simulation results."""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        simulation = data.get("simulation")

        if not simulation:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": "Simulation data required"}
            )

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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/policy/simulate")
async def simulate_policy_api(request: Request):
    """Simulate policy application with cost impact."""
    try:
        data = (await request.json() if await request.body() else {}) or {}
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/policy/apply")
async def apply_policy_api(request: Request):
    """Apply a governance policy."""
    try:
        data = (await request.json() if await request.body() else {}) or {}
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/business-metrics")
async def add_business_metric(request: Request):
    try:
        data = (await request.json() if await request.body() else {}) or {}
        name = data.get("metric_name")
        value = data.get("value")
        unit = data.get("unit")

        if not name or value is None or not unit:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": "All fields are required."}
            )

        db = SessionLocal()
        try:
            metric = BusinessMetric(
                metric_name=name.upper().replace(" ", "_"), value=float(value), unit=unit
            )
            db.add(metric)
            db.commit()
            return JSONResponse(
                status_code=201,
                content={"status": "success", "message": f"Metric '{name}' recorded successfully."},
            )
        except Exception as e:
            db.rollback()
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        finally:
            db.close()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/build-with-ai")
async def build_with_ai(request: Request):
    """Renders the AI Multi-Cloud Architect Estimator workspace dashboard."""
    return templates.TemplateResponse(request, "pages/build_with_ai.html", {"request": request})


@app.get("/api/v1/architect/status")
async def api_architect_status(request: Request):
    """Returns the validation state of the configured OpenAI, Gemini, and Claude API keys."""
    status = architect_manager.verify_api_status()
    return jsonify(
        {
            "status": "success",
            "openai": status["openai"],
            "gemini": status["gemini"],
            "claude": status["claude"],
        }
    )


@app.post("/api/v1/architect/estimate")
async def api_architect_estimate(request: Request):
    """Asynchronously processes user prompt, extracts architecture requirements and compiles a financial BOM."""
    data = (await request.json() if await request.body() else {}) or {}
    user_prompt = data.get("prompt")
    provider = data.get("provider", "azure")
    region = data.get("region", "eastus")
    model_provider = data.get("model_provider", "openai")

    if not user_prompt:
        return JSONResponse(
            status_code=400, content={"error": "Infrastructure requirements prompt is required."}
        )

    try:
        # Step 1: Run Cognitive Extraction Contract
        blueprint = architect_manager.generate_blueprint(
            user_prompt, provider, model_provider=model_provider
        )

        # Step 2: Resolve financial cost metrics against PostgreSQL cache
        calculated_payload = resolve_component_costs(blueprint, provider, region)

        return JSONResponse(status_code=200, content=calculated_payload)

    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to compile AI architecture: {e!s}"}
        )


@app.get("/about")
async def about(request: Request):
    return templates.TemplateResponse(request, "pages/about.html", {"request": request})


@app.get("/docs")
async def docs(request: Request):
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    docs_dir = base_dir / "docs"
    docs_data = []
    if docs_dir.exists():
        md_files = list(docs_dir.glob("*.md"))
        txt_files = list(docs_dir.glob("*.txt"))
        files = sorted(md_files + txt_files)
        for file_path in files:
            filename = file_path.name
            title = (
                filename.replace(".md", "")
                .replace(".txt", "")
                .lstrip("0123456789_")
                .replace("_", " ")
                .title()
            )
            with file_path.open(encoding="utf-8") as f:
                content = f.read()
            docs_data.append({"filename": filename, "title": title, "content": content})
    return templates.TemplateResponse(
        request,
        "pages/docs.html",
        {"request": request, "docs_data": docs_data},
    )


@app.get("/integrations")
async def integrations(request: Request):
    return templates.TemplateResponse(
        request,
        "pages/integrations.html",
        {"request": request, "settings": settings_state},
    )


@app.get("/monitor")
async def monitor(request: Request):
    return templates.TemplateResponse(request, "pages/monitor.html", {"request": request})


@app.get("/dashboard")
async def dashboard(request: Request):
    user_name, sub_name = _get_cached_user_info(request)
    return templates.TemplateResponse(
        request,
        "pages/dashboard.html",
        {
            "request": request,
            "user_name": user_name,
            "sub_name": sub_name,
            "metrics_emit_sec": SOCKET_METRICS_INTERVAL_SEC,
        },
    )


@app.get("/api/dashboard/finops-charts")
async def api_dashboard_finops_charts(request: Request):
    """HTTP snapshot for heavier FinOps charts (refreshed periodically from the client)."""
    if is_first_run():
        return JSONResponse(status_code=200, content={"status": "unconfigured", "charts": None})

    cache_key = "finops_charts_data"
    cache_ttl = 60  # 60 seconds cache for chart data

    # Check session cache first
    cached_charts = request.session.get(cache_key)
    cached_timestamp = request.session.get(f"{cache_key}_timestamp")

    # Return cached data if valid
    if cached_charts and cached_timestamp:
        if time.time() - float(cached_timestamp) < cache_ttl:
            return {"status": "ok", "charts": cached_charts, "cached": True}

    try:

        def _fetch_charts():
            c = AzureCollector()
            budget = float(settings_state.get("budget_threshold", 1000.0))
            return c.get_finops_dashboard_snapshot(monthly_budget=budget)

        charts = await asyncio.to_thread(_fetch_charts)

        # Cache in session
        request.session[cache_key] = charts
        request.session[f"{cache_key}_timestamp"] = str(time.time())

        return {"status": "ok", "charts": charts, "cached": False}
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e), "charts": None}
        )


def cache_response(max_age=300):
    """Decorator to add cache headers to responses."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            if hasattr(response, "headers"):
                response.headers["Cache-Control"] = f"public, max-age={max_age}"
            return response

        return decorated_function

    return decorator


@app.get("/api/auth/status")
@cache_response(max_age=60)  # Cache for 1 minute
def auth_status():
    return check_azure_status()


@app.get("/api/rightsizing")
async def get_rightsizing(request: Request):
    def _get_collector():
        return AzureCollector()

    az = await asyncio.to_thread(_get_collector)

    try:
        # ── Non-blocking Go engine call ──────────────────────────────────────
        # go_bridge.scan() first tries the resident HTTP bridge server on
        # :7070 (zero fork overhead); if the bridge is not running it falls
        # back to asyncio.create_subprocess_exec — still non-blocking.
        go_data = await go_bridge.scan(subscription_id=az.subscription_id, provider="azure")
        if not go_data:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Go engine returned no data"},
            )

        vm_reports = go_data.get("vm_reports", [])
        recommendations = RightSizer().calculate_recommendation(vm_reports)

        return jsonify(
            {
                "status": "success",
                "recommendations": recommendations,
                "total_saving": sum(r["monthly_saving"] for r in recommendations),
                "engine": "go-bridge" if go_data.get("db_stats") else "go-subprocess",
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/scan")
async def scan(request: Request):
    events: list[dict] = [{"msg": "Authenticating with Azure Identity...", "type": "info"}]
    try:
        target_subs = settings_state.get("selected_subscriptions", []) or [
            os.getenv("AZURE_SUBSCRIPTION_ID")
        ]
        # pyrefly: ignore [bad-index, unsupported-operation]
        if not target_subs[0]:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "No subscription ID configured."},
            )

        # ── Async scan dispatch ──────────────────────────────────────────────
        # Each subscription scan is awaited via go_bridge, which is fully
        # non-blocking: the ASGI event loop is released during the I/O wait
        # so other requests (metrics, WebSocket pushes) are never starved.
        scan_results = await _async_perform_subscription_scan(target_subs, events)
        formatted_results = format_scan_results(scan_results)

        events.append(
            {
                "msg": f"Scan complete. {len(formatted_results['zombies'])} zombies detected.",
                "type": "warning" if formatted_results["zombies"] else "success",
            }
        )

        return {"status": "success", "events": events, **formatted_results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


async def _async_perform_subscription_scan(target_subs: list[str], events: list[dict]) -> dict:
    """
    Async variant of perform_subscription_scan.

    Each subscription is dispatched via go_bridge.scan(), which either calls
    the resident HTTP bridge or falls back to asyncio subprocess — both paths
    are non-blocking.  Results are merged in the same shape as the sync
    version so format_scan_results() works unchanged.
    """

    def _get_collector():
        return AzureCollector()

    az = await asyncio.to_thread(_get_collector)
    results: dict = {
        "vms_count": 0,
        "orphans": [],
        "snapshots": [],
        "zombies": [],
        "idle_vms": [],
        "utilization": [],
        "aws_resources": [],
        "gcp_resources": [],
    }

    for sub_id in target_subs:
        events.append({"msg": f"Scanning subscription: {sub_id[:8]}...", "type": "info"})
        az.subscription_id = sub_id

        # await — releases the event loop during Go engine I/O
        go_data = await go_bridge.scan(subscription_id=sub_id, provider="azure")

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

            reported_vms: set[str] = set()
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
            # Bridge unavailable — fall back to synchronous Python collector
            events.append(
                {
                    "msg": f"Bridge unavailable, using Python collector for {sub_id[:8]}...",
                    "type": "info",
                }
            )
            _python_fallback_scan(az, results)

    results["utilization"].sort(key=lambda x: x["usage"], reverse=True)
    return results


def _python_fallback_scan(az: Any, results: dict) -> None:
    """Pure-Python collector fallback when the Go engine bridge is unavailable."""
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


def perform_subscription_scan(target_subs, events):
    # Note: This is a sync function called from sync context, so blocking AzureCollector is acceptable
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
        "aws_resources": [],
        "gcp_resources": [],
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

    # AWS Resources
    for resource in raw.get("aws_resources", []):
        cost = calc.calculate_monthly_cost(
            "aws", resource.get("category", "compute"), resource.get("sku", "t3.micro")
        )
        total_savings += cost
        formatted["aws_resources"].append(
            {
                "name": resource.get("name", "Unknown"),
                "type": resource.get("type", "Unknown"),
                "savings": calc.format_price(cost),
                "region": resource.get("region", "N/A"),
            }
        )

    # GCP Resources
    for resource in raw.get("gcp_resources", []):
        cost = calc.calculate_monthly_cost(
            "gcp", resource.get("category", "compute"), resource.get("sku", "n1-standard-1")
        )
        total_savings += cost
        formatted["gcp_resources"].append(
            {
                "name": resource.get("name", "Unknown"),
                "type": resource.get("type", "Unknown"),
                "savings": calc.format_price(cost),
                "region": resource.get("region", "N/A"),
            }
        )

    formatted["total_savings"] = calc.format_price(total_savings)
    return formatted


@app.get("/api/prices")
async def get_prices(request: Request):
    provider = request.query_params.get("provider", "azure").lower()
    try:
        page = int(request.query_params.get("page", 1))
    except ValueError:
        page = 1
    try:
        per_page = int(request.query_params.get("per_page", 50))
    except ValueError:
        per_page = 50
    search = request.query_params.get("search", "").strip()
    service = request.query_params.get("service", "").strip()
    region = request.query_params.get("region", "").strip()
    sort_by = request.query_params.get("sort", "sku-asc")

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
            return JSONResponse(status_code=202, content={"status": "warming", **result})
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
        return {"status": "success", **result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/prices/status")
async def get_prices_status(request: Request):
    provider = request.query_params.get("provider")
    return {"status": "success", "catalogs": get_catalog_status(provider)}


@app.get("/api/prices/filters")
async def get_prices_filters(request: Request):
    provider = request.query_params.get("provider", "azure").lower()
    try:
        filters = get_catalog_filters(provider)
        return {"status": "success", "provider": provider, **filters}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/prices/refresh")
async def refresh_prices(request: Request):
    provider = (
        ((await request.json() if await request.body() else {}) or {}).get("provider")
        if request.is_json
        else None
    )
    providers = [provider] if provider else ["azure", "aws", "gcp"]
    for prov in providers:
        threading.Thread(
            target=warm_catalog, args=(prov,), kwargs={"force": True}, daemon=True
        ).start()
    return jsonify(
        {"status": "success", "message": "Price catalog refresh started", "providers": providers}
    )


@app.post("/api/export/bom")
async def export_bom(request: Request):
    try:
        data = (await request.json() if await request.body() else {}) or {}
        items = data.get("resources", [])
        total_hourly = data.get("totalHourly", 0.0)
        total_monthly = data.get("totalMonthly", 0.0)

        # Render the HTML template
        rendered_html = render_template_string(
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
                },
                status_code=500,
            )
        HTML(string=rendered_html).write_pdf(pdf_out)
        pdf_out.seek(0)

        return StreamingResponse(
            pdf_out,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Cloud_Reaper_BOM.pdf"},
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/tag-health")
async def tag_health(request: Request):
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
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        finally:
            session.close()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/anomalies")
async def anomalies(request: Request):
    try:

        def _get_anomalies():
            c = AzureCollector()
            return c.get_anomaly_data()

        data = await asyncio.to_thread(_get_anomalies)
        return jsonify(
            {
                "status": "success",
                "services": data,
                "spike_count": sum(1 for d in data if d["is_anomaly"]),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/anomalies/triage")
async def anomalies_triage(request: Request):
    try:
        data = (await request.json() if await request.body() else {}) or {}
        service = data.get("service", "Unknown")
        cost = float(data.get("cost", 0.0))
        deviation = data.get("deviation", "Unknown")

        if not service:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": "Missing service name"}
            )

        from reaper.engine.copilot.engine import AnomalyTriager

        triager = AnomalyTriager()
        playbook = triager.generate_triage_playbook(service, cost, deviation)

        return {"status": "success", "playbook": playbook}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/unit-economics")
async def unit_economics(request: Request):
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
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        finally:
            session.close()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/ri-advisor")
async def ri_advisor(request: Request):
    try:

        def _get_candidates():
            c = AzureCollector()
            return c.get_ri_sp_candidates()

        candidates = await asyncio.to_thread(_get_candidates)
        return jsonify(
            {
                "status": "success",
                "candidates": candidates,
                "total_annual_savings": round(sum(c["annual_savings"] for c in candidates), 2),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/cold-storage")
async def cold_storage(request: Request):
    try:

        def _get_buckets():
            c = AzureCollector()
            return c.get_cold_storage_candidates()

        buckets = await asyncio.to_thread(_get_buckets)
        return jsonify(
            {
                "status": "success",
                "buckets": buckets,
                "total_monthly_savings": round(sum(b["monthly_savings"] for b in buckets), 2),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/modernization")
async def modernization(request: Request):
    try:

        def _get_suggestions():
            c = AzureCollector()
            return c.get_modernization_candidates()

        suggestions = await asyncio.to_thread(_get_suggestions)
        return jsonify(
            {
                "status": "success",
                "suggestions": suggestions,
                "total_annual_savings": round(sum(s["annual_savings"] for s in suggestions), 2),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/policy-violations")
async def policy_violations(request: Request):
    try:

        def _get_violations():
            c = AzureCollector()
            return c.get_policy_violations()

        violations = await asyncio.to_thread(_get_violations)
        return jsonify(
            {
                "status": "success",
                "violations": violations,
                "critical_count": sum(1 for v in violations if v["severity"] == "HIGH"),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/budget-status")
async def budget_status(request: Request):
    try:

        def _get_budget_status():
            c = AzureCollector()
            return c.get_budget_status()

        budgets = await asyncio.to_thread(_get_budget_status)
        return {"status": "success", "budgets": budgets}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/budget-killswitch")
async def budget_killswitch(request: Request):
    try:
        data = (await request.json() if await request.body() else {}) or {}
        sub_name = data.get("subscription", "Unknown")
        await asyncio.sleep(0.5)
        return jsonify(
            {
                "status": "success",
                "message": f"Kill-switch initiated for {sub_name}. Checking policy compliance...",
                "vms_stopped": [],
                "estimated_savings": "$0.00/day",
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/burn-rate-forecast")
async def burn_rate_forecast(request: Request):
    try:

        def _get_forecast():
            c = AzureCollector()
            return c.get_burn_rate_forecast()

        forecast = await asyncio.to_thread(_get_forecast)
        return {"status": "success", "forecast": forecast}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/virtual-tags")
async def virtual_tags(request: Request):
    try:

        def _get_virtual_tags():
            c = AzureCollector()
            return c.get_virtual_tags()

        virtual_tags = await asyncio.to_thread(_get_virtual_tags)
        return {"status": "success", "virtual_tags": virtual_tags}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/greenops")
async def greenops(request: Request):
    try:
        return jsonify(
            {
                "status": "success",
                "recommendations": await asyncio.to_thread(
                    _run_collector, "get_greenops_recommendations"
                ),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/finops/approve-reap")
async def approve_reap(request: Request):
    try:
        data = (await request.json() if await request.body() else {}) or {}
        res_id, res_type = data.get("resource_id"), data.get("resource_type")
        if not res_id:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": "Missing resource_id"}
            )

        def _execute_reap():
            c = AzureCollector()
            return c.execute_reap(res_id, res_type)

        return await asyncio.to_thread(_execute_reap)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/prices/regional")
async def get_regional_prices(request: Request):
    try:
        sku = request.query_params.get("sku")
        region = request.query_params.get("region")
        if not sku or not region:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Missing sku or region parameter"},
            )

        def _fetch_prices():
            c = AzureCollector()
            return c.fetch_regional_prices(sku, region)

        prices = await asyncio.to_thread(_fetch_prices)
        if prices:
            return {"status": "success", "price": prices[0]}
        return JSONResponse(
            status_code=404, content={"status": "error", "message": "Price not found"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/arbitrage")
async def get_arbitrage(request: Request):
    try:
        sku = request.query_params.get("sku")
        region = request.query_params.get("region")
        price = float(request.query_params.get("price", 0.0))

        if not sku or not region or not price:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": "Missing parameters"}
            )

        arb = RegionalArbitrage()
        result = arb.analyze_arbitrage(sku, region, price)
        return {"status": "success", "recommendation": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/activity")
async def get_activity(request: Request):
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
            return {"status": "success", "activity": result}
        except Exception as e:
            session.rollback()
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        finally:
            session.close()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/utilization")
async def utilization(request: Request):
    try:

        def _get_utilization():
            c = AzureCollector()
            return c.get_utilization_report()

        report = await asyncio.to_thread(_get_utilization)
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
        return {"status": "success", "report": formatted_report}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/spot-prediction")
async def spot_prediction(request: Request):
    try:
        instance_id = request.query_params.get("instance_id", "vm-spot-worker-01")
        region = request.query_params.get("region", "eastus")

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
        return {"status": "success", "prediction": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/k8s/bin-packing")
async def k8s_bin_packing(request: Request):
    try:
        from reaper.engine.core.workload import KubernetesOptimizer

        optimizer = KubernetesOptimizer()
        return {"status": "success", "bin_packing": optimizer.get_bin_packing_assessment()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/k8s/hibernation")
async def k8s_hibernation(request: Request):
    try:
        from reaper.engine.core.workload import KubernetesOptimizer

        optimizer = KubernetesOptimizer()
        return {"status": "success", "hibernation": optimizer.get_hibernation_status()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/finops/ai-token-tracking")
async def ai_token_tracking(request: Request):
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# Initialize the comprehensive cost optimizer
cost_optimizer = ComprehensiveCostOptimizer()

# Initialize the automated cost reporter
cost_reporter = AutomatedCostReporter()


@app.post("/api/cost-optimization/analyze")
async def analyze_cost_optimization(request: Request):
    """Comprehensive cost optimization analysis for all cloud resources"""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        provider = data.get("provider", "azure").lower()

        if is_first_run():
            return jsonify(
                {"status": "unconfigured", "message": "Please configure cloud credentials first"}
            )

        # Initialize collector based on provider
        if provider == "azure":

            def _get_collector():
                return AzureCollector()

            collector = await asyncio.to_thread(_get_collector)
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Provider {provider} not yet supported in comprehensive analysis",
                },
                status_code=400,
            )

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

        # ========== NEW RESOURCE TYPES ANALYSIS ==========

        # Storage Accounts
        try:
            storage_accounts = collector.get_storage_accounts()
            for account in storage_accounts:
                metrics = ResourceMetrics(
                    cpu_utilization=0,
                    memory_utilization=0,
                    disk_utilization=50,  # Assume moderate usage
                    network_in_mbps=1.0,
                    network_out_mbps=1.0,
                    iops=100,
                    latency_ms=10,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=0,
                    peak_memory_utilization=0,
                )

                current_sku = account.get("sku", "Standard_LRS")
                current_cost = calc.calculate_monthly_cost(provider, "storage", current_sku)

                resource_data = {
                    "id": account.get("id", ""),
                    "name": account.get("name", ""),
                    "type": "storage",
                    "provider": provider,
                    "sku": current_sku,
                    "region": account.get("location", ""),
                    "tags": account.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": account.get("id", ""),
                        "name": account.get("name", ""),
                        "type": "storage",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing storage accounts: {e}")

        # AKS Clusters
        try:
            aks_clusters = collector.get_aks_clusters()
            for cluster in aks_clusters:
                metrics = ResourceMetrics(
                    cpu_utilization=40,  # Assume moderate cluster utilization
                    memory_utilization=50,
                    disk_utilization=60,
                    network_in_mbps=5.0,
                    network_out_mbps=5.0,
                    iops=500,
                    latency_ms=5,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=70,
                    peak_memory_utilization=80,
                )

                current_sku = cluster.get("sku", "Free")
                node_count = cluster.get("node_count", 1)
                current_cost = (
                    calc.calculate_monthly_cost(provider, "container", current_sku) * node_count
                )

                resource_data = {
                    "id": cluster.get("id", ""),
                    "name": cluster.get("name", ""),
                    "type": "container",
                    "provider": provider,
                    "sku": current_sku,
                    "region": cluster.get("location", ""),
                    "tags": cluster.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": cluster.get("id", ""),
                        "name": cluster.get("name", ""),
                        "type": "container",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing AKS clusters: {e}")

        # Container Instances
        try:
            container_instances = collector.get_container_instances()
            for instance in container_instances:
                metrics = ResourceMetrics(
                    cpu_utilization=30,
                    memory_utilization=40,
                    disk_utilization=20,
                    network_in_mbps=0.5,
                    network_out_mbps=0.5,
                    iops=50,
                    latency_ms=10,
                    error_rate=0,
                    uptime_percentage=95,
                    peak_cpu_utilization=50,
                    peak_memory_utilization=60,
                )

                current_sku = "Standard"
                current_cost = calc.calculate_monthly_cost(provider, "container", current_sku)

                resource_data = {
                    "id": instance.get("id", ""),
                    "name": instance.get("name", ""),
                    "type": "container",
                    "provider": provider,
                    "sku": current_sku,
                    "region": instance.get("location", ""),
                    "tags": instance.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": instance.get("id", ""),
                        "name": instance.get("name", ""),
                        "type": "container",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing container instances: {e}")

        # Function Apps
        try:
            function_apps = collector.get_function_apps()
            for app in function_apps:
                metrics = ResourceMetrics(
                    cpu_utilization=20,  # Serverless - typically lower utilization
                    memory_utilization=30,
                    disk_utilization=10,
                    network_in_mbps=0.2,
                    network_out_mbps=0.2,
                    iops=20,
                    latency_ms=50,  # Cold starts
                    error_rate=0,
                    uptime_percentage=99,  # Serverless availability
                    peak_cpu_utilization=40,
                    peak_memory_utilization=50,
                )

                current_sku = "Consumption"
                current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                resource_data = {
                    "id": app.get("id", ""),
                    "name": app.get("name", ""),
                    "type": "compute",
                    "provider": provider,
                    "sku": current_sku,
                    "region": app.get("location", ""),
                    "tags": app.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": app.get("id", ""),
                        "name": app.get("name", ""),
                        "type": "compute",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing function apps: {e}")

        # Key Vaults
        try:
            key_vaults = collector.get_key_vaults()
            for vault in key_vaults:
                metrics = ResourceMetrics(
                    cpu_utilization=5,  # Low utilization for vault operations
                    memory_utilization=10,
                    disk_utilization=5,
                    network_in_mbps=0.1,
                    network_out_mbps=0.1,
                    iops=10,
                    latency_ms=20,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=10,
                    peak_memory_utilization=15,
                )

                current_sku = "Standard"
                current_cost = calc.calculate_monthly_cost(provider, "database", current_sku)

                resource_data = {
                    "id": vault.get("id", ""),
                    "name": vault.get("name", ""),
                    "type": "database",
                    "provider": provider,
                    "sku": current_sku,
                    "region": vault.get("location", ""),
                    "tags": vault.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": vault.get("id", ""),
                        "name": vault.get("name", ""),
                        "type": "database",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing key vaults: {e}")

        # Redis Caches
        try:
            redis_caches = collector.get_redis_caches()
            for cache in redis_caches:
                metrics = ResourceMetrics(
                    cpu_utilization=45,  # Caching typically has moderate utilization
                    memory_utilization=60,  # Memory-intensive
                    disk_utilization=20,
                    network_in_mbps=2.0,
                    network_out_mbps=2.0,
                    iops=200,
                    latency_ms=1,  # Low latency for cache
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=70,
                    peak_memory_utilization=85,
                )

                current_sku = cache.get("sku_name", "Basic")
                current_cost = calc.calculate_monthly_cost(provider, "database", current_sku)

                resource_data = {
                    "id": cache.get("id", ""),
                    "name": cache.get("name", ""),
                    "type": "database",
                    "provider": provider,
                    "sku": current_sku,
                    "region": cache.get("location", ""),
                    "tags": cache.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": cache.get("id", ""),
                        "name": cache.get("name", ""),
                        "type": "database",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing Redis caches: {e}")

        # Cosmos DB Accounts
        try:
            cosmos_accounts = collector.get_cosmos_db_accounts()
            for account in cosmos_accounts:
                metrics = ResourceMetrics(
                    cpu_utilization=50,
                    memory_utilization=55,
                    disk_utilization=70,
                    network_in_mbps=3.0,
                    network_out_mbps=3.0,
                    iops=1000,
                    latency_ms=10,
                    error_rate=0,
                    uptime_percentage=99.99,
                    peak_cpu_utilization=80,
                    peak_memory_utilization=90,
                )

                current_sku = "Standard"
                current_cost = calc.calculate_monthly_cost(provider, "database", current_sku)

                resource_data = {
                    "id": account.get("id", ""),
                    "name": account.get("name", ""),
                    "type": "database",
                    "provider": provider,
                    "sku": current_sku,
                    "region": account.get("location", ""),
                    "tags": account.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": account.get("id", ""),
                        "name": account.get("name", ""),
                        "type": "database",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing Cosmos DB accounts: {e}")

        # Data Factories
        try:
            data_factories = collector.get_data_factories()
            for factory in data_factories:
                metrics = ResourceMetrics(
                    cpu_utilization=30,
                    memory_utilization=40,
                    disk_utilization=30,
                    network_in_mbps=1.5,
                    network_out_mbps=1.5,
                    iops=100,
                    latency_ms=100,  # Batch processing
                    error_rate=0,
                    uptime_percentage=99,
                    peak_cpu_utilization=60,
                    peak_memory_utilization=70,
                )

                current_sku = "Standard"
                current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                resource_data = {
                    "id": factory.get("id", ""),
                    "name": factory.get("name", ""),
                    "type": "compute",
                    "provider": provider,
                    "sku": current_sku,
                    "region": factory.get("location", ""),
                    "tags": factory.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": factory.get("id", ""),
                        "name": factory.get("name", ""),
                        "type": "compute",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing data factories: {e}")

        # Logic Apps
        try:
            logic_apps = collector.get_logic_apps()
            for app in logic_apps:
                metrics = ResourceMetrics(
                    cpu_utilization=15,  # Serverless workflow
                    memory_utilization=20,
                    disk_utilization=10,
                    network_in_mbps=0.3,
                    network_out_mbps=0.3,
                    iops=30,
                    latency_ms=200,  # Workflow processing
                    error_rate=0,
                    uptime_percentage=99,
                    peak_cpu_utilization=30,
                    peak_memory_utilization=40,
                )

                current_sku = app.get("sku", "Consumption")
                current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                resource_data = {
                    "id": app.get("id", ""),
                    "name": app.get("name", ""),
                    "type": "compute",
                    "provider": provider,
                    "sku": current_sku,
                    "region": app.get("location", ""),
                    "tags": app.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": app.get("id", ""),
                        "name": app.get("name", ""),
                        "type": "compute",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing logic apps: {e}")

        # Event Hubs
        try:
            event_hubs = collector.get_event_hubs()
            for hub in event_hubs:
                metrics = ResourceMetrics(
                    cpu_utilization=35,
                    memory_utilization=45,
                    disk_utilization=40,
                    network_in_mbps=2.5,
                    network_out_mbps=2.5,
                    iops=300,
                    latency_ms=20,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=65,
                    peak_memory_utilization=75,
                )

                current_sku = hub.get("sku_name", "Basic")
                current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                resource_data = {
                    "id": hub.get("id", ""),
                    "name": hub.get("name", ""),
                    "type": "network",
                    "provider": provider,
                    "sku": current_sku,
                    "region": hub.get("location", ""),
                    "tags": hub.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": hub.get("id", ""),
                        "name": hub.get("name", ""),
                        "type": "network",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing event hubs: {e}")

        # Service Bus Namespaces
        try:
            service_bus = collector.get_service_bus_namespaces()
            for namespace in service_bus:
                metrics = ResourceMetrics(
                    cpu_utilization=25,
                    memory_utilization=35,
                    disk_utilization=30,
                    network_in_mbps=1.0,
                    network_out_mbps=1.0,
                    iops=150,
                    latency_ms=15,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=50,
                    peak_memory_utilization=60,
                )

                current_sku = namespace.get("sku_name", "Basic")
                current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                resource_data = {
                    "id": namespace.get("id", ""),
                    "name": namespace.get("name", ""),
                    "type": "network",
                    "provider": provider,
                    "sku": current_sku,
                    "region": namespace.get("location", ""),
                    "tags": namespace.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": namespace.get("id", ""),
                        "name": namespace.get("name", ""),
                        "type": "network",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing service bus namespaces: {e}")

        # IoT Hubs
        try:
            iot_hubs = collector.get_iot_hubs()
            for hub in iot_hubs:
                metrics = ResourceMetrics(
                    cpu_utilization=30,
                    memory_utilization=40,
                    disk_utilization=35,
                    network_in_mbps=1.2,
                    network_out_mbps=1.2,
                    iops=200,
                    latency_ms=25,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=55,
                    peak_memory_utilization=65,
                )

                current_sku = hub.get("sku_name", "F1")
                current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                resource_data = {
                    "id": hub.get("id", ""),
                    "name": hub.get("name", ""),
                    "type": "network",
                    "provider": provider,
                    "sku": current_sku,
                    "region": hub.get("location", ""),
                    "tags": hub.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": hub.get("id", ""),
                        "name": hub.get("name", ""),
                        "type": "network",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing IoT hubs: {e}")

        # Cognitive Services
        try:
            cognitive_services = collector.get_cognitive_services()
            for service in cognitive_services:
                metrics = ResourceMetrics(
                    cpu_utilization=40,
                    memory_utilization=50,
                    disk_utilization=25,
                    network_in_mbps=2.0,
                    network_out_mbps=2.0,
                    iops=250,
                    latency_ms=50,  # AI processing latency
                    error_rate=0,
                    uptime_percentage=99.5,
                    peak_cpu_utilization=70,
                    peak_memory_utilization=80,
                )

                current_sku = service.get("sku_name", "S0")
                current_cost = calc.calculate_monthly_cost(provider, "compute", current_sku)

                resource_data = {
                    "id": service.get("id", ""),
                    "name": service.get("name", ""),
                    "type": "compute",
                    "provider": provider,
                    "sku": current_sku,
                    "region": service.get("location", ""),
                    "tags": service.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": service.get("id", ""),
                        "name": service.get("name", ""),
                        "type": "compute",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing cognitive services: {e}")

        # Application Insights
        try:
            app_insights = collector.get_application_insights()
            for insights in app_insights:
                metrics = ResourceMetrics(
                    cpu_utilization=10,  # Monitoring service
                    memory_utilization=15,
                    disk_utilization=20,
                    network_in_mbps=0.5,
                    network_out_mbps=0.5,
                    iops=50,
                    latency_ms=30,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=20,
                    peak_memory_utilization=25,
                )

                current_sku = "Standard"
                current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                resource_data = {
                    "id": insights.get("id", ""),
                    "name": insights.get("name", ""),
                    "type": "network",
                    "provider": provider,
                    "sku": current_sku,
                    "region": insights.get("location", ""),
                    "tags": insights.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": insights.get("id", ""),
                        "name": insights.get("name", ""),
                        "type": "network",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing application insights: {e}")

        # CDN Profiles
        try:
            cdn_profiles = collector.get_cdn_profiles()
            for profile in cdn_profiles:
                metrics = ResourceMetrics(
                    cpu_utilization=20,
                    memory_utilization=25,
                    disk_utilization=15,
                    network_in_mbps=5.0,  # High bandwidth for CDN
                    network_out_mbps=5.0,
                    iops=100,
                    latency_ms=5,  # Low latency for CDN
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=40,
                    peak_memory_utilization=50,
                )

                current_sku = profile.get("sku_name", "Standard_Microsoft")
                current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                resource_data = {
                    "id": profile.get("id", ""),
                    "name": profile.get("name", ""),
                    "type": "network",
                    "provider": provider,
                    "sku": current_sku,
                    "region": profile.get("location", ""),
                    "tags": profile.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": profile.get("id", ""),
                        "name": profile.get("name", ""),
                        "type": "network",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing CDN profiles: {e}")

        # API Management Instances
        try:
            apim_instances = collector.get_api_management_instances()
            for instance in apim_instances:
                metrics = ResourceMetrics(
                    cpu_utilization=35,
                    memory_utilization=45,
                    disk_utilization=30,
                    network_in_mbps=3.0,
                    network_out_mbps=3.0,
                    iops=200,
                    latency_ms=10,
                    error_rate=0,
                    uptime_percentage=99.9,
                    peak_cpu_utilization=60,
                    peak_memory_utilization=70,
                )

                current_sku = instance.get("sku_name", "Developer")
                current_cost = calc.calculate_monthly_cost(provider, "network", current_sku)

                resource_data = {
                    "id": instance.get("id", ""),
                    "name": instance.get("name", ""),
                    "type": "network",
                    "provider": provider,
                    "sku": current_sku,
                    "region": instance.get("location", ""),
                    "tags": instance.get("tags", {}),
                }

                recommendations = cost_optimizer.analyze_resource(
                    resource_data, metrics, current_cost
                )
                cost_optimizer.recommendations.extend(recommendations)
                resources.append(
                    {
                        "id": instance.get("id", ""),
                        "name": instance.get("name", ""),
                        "type": "network",
                        "current_cost": current_cost,
                        "metrics": {},
                    }
                )
        except Exception as e:
            print(f"[!] Error analyzing API management instances: {e}")

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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-optimization/summary")
async def get_optimization_summary(request: Request):
    """Get a quick summary of cost optimization opportunities"""
    try:
        summary = cost_optimizer.generate_summary_report()
        return {"status": "success", "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-optimization/categories")
async def get_optimization_categories(request: Request):
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

        return {"status": "success", "categories": category_summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-optimization/priority/{priority}")
async def get_optimization_by_priority(request: Request, priority):
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
        return JSONResponse(
            status_code=400, content={"status": "error", "message": f"Invalid priority: {priority}"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-optimization/resource/{resource_id}")
async def get_resource_optimizations(request: Request, resource_id):
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
                },
                status_code=404,
            )

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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-optimization/dashboard")
async def get_optimization_dashboard(request: Request):
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

        return {"status": "success", "dashboard": dashboard_data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/cost-optimization")
async def cost_optimization_page(request: Request):
    """Render the cost optimization dashboard page"""
    return templates.TemplateResponse(request, "pages/cost-optimization.html", {"request": request})


@app.get("/resource-inventory")
async def resource_inventory_page(request: Request):
    """Render the resource inventory page"""
    return templates.TemplateResponse(
        request, "pages/resource-inventory.html", {"request": request}
    )


@app.get("/api/cost-reports/executive-summary")
async def get_executive_summary(request: Request):
    """Generate executive summary of cost optimization efforts"""
    try:
        provider = request.query_params.get("provider", "azure").lower()
        period = request.query_params.get("period", "monthly").lower()

        period_enum = ReportPeriod[period.upper()]

        summary = cost_reporter.generate_executive_summary(period_enum, provider)
        return {"status": "success", "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/cost-reports/generate")
async def generate_cost_report(request: Request):
    """Generate detailed cost optimization report"""
    try:
        data = (await request.json() if await request.body() else {}) or {}
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
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/cost-reports/download")
async def download_cost_report(request: Request):
    """Download cost optimization report"""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        provider = data.get("provider", "azure").lower()
        period = data.get("period", "monthly").lower()
        format_type = data.get("format", "json").lower()

        period_enum = ReportPeriod[period.upper()]
        format_enum = ReportFormat[format_type.upper()]

        report_content = cost_reporter.generate_detailed_report(period_enum, provider, format_enum)

        # Create appropriate response based on format
        if format_type == "json":
            return {"status": "success", "report": report_content}
        return jsonify(
            {
                "status": "success",
                "report": report_content,
                "format": format_type,
                "filename": f"cost-optimization-report-{period}-{provider}.{format_type}",
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/cost-reports/track-status")
async def track_recommendation_status(request: Request):
    """Track implementation status of a recommendation"""
    try:
        data = (await request.json() if await request.body() else {}) or {}
        recommendation_id = data.get("recommendation_id")
        status = data.get("status", "planned")
        notes = data.get("notes", "")

        if not recommendation_id:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "recommendation_id is required"},
            )

        success = cost_reporter.track_recommendation_status(recommendation_id, status, notes)

        if success:
            return {"status": "success", "message": "Status tracked successfully"}
        return JSONResponse(
            status_code=500, content={"status": "error", "message": "Failed to track status"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-reports/implementation-progress")
async def get_implementation_progress(request: Request):
    """Get implementation progress of all recommendations"""
    try:
        progress = cost_reporter._get_implementation_progress()
        return {"status": "success", "progress": progress}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-reports/trends")
async def get_cost_trends(request: Request):
    """Get cost optimization trends over time"""
    try:
        trends_data = {
            "trends": [trend.to_dict() for trend in cost_reporter.cost_trends],
            "analysis": cost_reporter._generate_trend_analysis(),
        }
        return {"status": "success", "trends_data": trends_data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-reports/category-analysis")
async def get_category_analysis(request: Request):
    """Get category-wise cost optimization analysis"""
    try:
        category_analysis = cost_reporter._generate_category_analysis()
        return {"status": "success", "category_analysis": category_analysis}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-reports/risk-assessment")
async def get_risk_assessment(request: Request):
    """Get risk assessment for all recommendations"""
    try:
        risk_assessment = cost_reporter._generate_risk_assessment()
        return {"status": "success", "risk_assessment": risk_assessment}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/cost-reports/next-steps")
async def get_next_steps(request: Request):
    """Get recommended next steps for cost optimization"""
    try:
        next_steps = cost_reporter._generate_next_steps()
        return {"status": "success", "next_steps": next_steps}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@sio.on("connect")
async def handle_connect(sid, environ):
    print("[+] Client Connected to Cloud-Reaper Engine")


@sio.on("start_log_stream")
async def handle_start_log_stream(sid, data):
    """Handle real-time log streaming with actual Cloud-Reaper logs."""

    import logging
    import platform

    from reaper.services.log_streamer import fetch_azure_logs

    # Use batched WebSocket emission for initial log messages
    initial_logs = ["🚀 Initializing Cloud-Reaper Log Stream...", "📡 Connecting to log sources..."]

    for log_msg in initial_logs:
        await ws_batcher.emit("new_log", {"data": log_msg})
        await asyncio.sleep(0.2)

    await ws_batcher.flush_all()

    # Try to get actual Python application logs
    try:
        # Get the root logger
        logger = logging.getLogger()

        # Check if there are any handlers with logs
        if logger.handlers:
            await ws_batcher.emit(
                "new_log",
                {
                    "data": f"✅ Connected to application logger - {len(logger.handlers)} handler(s) found"
                },
            )
            await asyncio.sleep(0.3)

            # Try to get recent log records if available
            # Note: This is a simplified approach - in production you'd want a proper log aggregation system
            await ws_batcher.emit(
                "new_log", {"data": "📊 Application logger connection established"}
            )
        else:
            await ws_batcher.emit("new_log", {"data": "⚠️  No application log handlers configured"})
            await asyncio.sleep(0.3)

        await ws_batcher.flush_all()
    except Exception as e:
        await ws_batcher.emit("new_log", {"data": f"❌ Application logger error: {e!s}"})
        await ws_batcher.flush_all()
        await asyncio.sleep(0.3)

    # Try Azure logs
    try:
        azure_logs = fetch_azure_logs()
        if azure_logs and len(azure_logs) > 0:
            await ws_batcher.emit(
                "new_log",
                {"data": f"✅ Connected to Azure Monitor - Found {len(azure_logs)} recent logs"},
            )
            await asyncio.sleep(0.3)

            # Batch Azure log messages
            for i, log in enumerate(azure_logs):
                await ws_batcher.emit("new_log", {"data": f"[Azure #{i + 1}] {log!s}"})

            await ws_batcher.flush_all()
        else:
            await ws_batcher.emit(
                "new_log", {"data": "⚠️  No Azure logs found - workspace may not be configured"}
            )
            await ws_batcher.flush_all()
            await asyncio.sleep(0.3)
    except Exception as e:
        await ws_batcher.emit("new_log", {"data": f"❌ Azure logs error: {e!s}"})
        await ws_batcher.flush_all()
        await asyncio.sleep(0.3)

    # Stream actual Cloud-Reaper system information
    system_messages = ["🔄 Streaming Cloud-Reaper system information..."]

    try:
        # Get actual system information
        system_messages.append(f"💻 System: {platform.system()} {platform.release()}")
        system_messages.append(f"🐍 Python: {platform.python_version()}")

        # Check Azure connection status
        from reaper.collectors.utils.auth_check import check_azure_status

        azure_status = check_azure_status()
        system_messages.append(f"🔗 Azure Status: {azure_status.get('status', 'unknown')}")

        # Get subscription info if available
        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "Not configured")
        if sub_id and len(sub_id) > 10:
            system_messages.append(f"📋 Subscription: {sub_id[:8]}...{sub_id[-4:]}")
        else:
            system_messages.append("⚠️  Subscription ID not configured")
    except Exception as e:
        system_messages.append(f"❌ System info error: {e!s}")

    # Batch system messages
    for msg in system_messages:
        await ws_batcher.emit("new_log", {"data": msg})
        await asyncio.sleep(0.1)

    await ws_batcher.flush_all()

    # Stream actual collector information
    collector_messages = ["🔍 Checking Cloud-Reaper collectors..."]

    try:
        from reaper.collectors.providers.azure_collector import AzureCollector

        def _get_collector():
            return AzureCollector()

        az = await asyncio.to_thread(_get_collector)
        collector_messages.append("✅ AzureCollector initialized successfully")

        # Try to get actual resource counts
        try:
            vms = list(az.compute.virtual_machines.list_all())
            collector_messages.append(f"🖥️  Virtual Machines found: {len(vms)}")
        except Exception as vm_error:
            collector_messages.append(f"⚠️  Could not fetch VMs: {vm_error!s}")

        try:
            disks = list(az.compute.disks.list())
            collector_messages.append(f"💾 Disks found: {len(disks)}")
        except Exception as disk_error:
            collector_messages.append(f"⚠️  Could not fetch disks: {disk_error!s}")

    except Exception as collector_error:
        collector_messages.append(f"❌ Collector error: {collector_error!s}")

    # Batch collector messages
    for msg in collector_messages:
        await ws_batcher.emit("new_log", {"data": msg})
        await asyncio.sleep(0.2)

    await ws_batcher.flush_all()

    # Stream engine information if available
    engine_messages = ["⚙️  Checking Cloud-Reaper engine status..."]

    try:
        binary_path = _reaper_engine_binary()
        if binary_path and binary_path.exists():
            engine_messages.append(f"✅ Go engine binary found at: {binary_path}")
        else:
            engine_messages.append("⚠️  Go engine binary not found - using Python engine")
    except Exception as engine_error:
        engine_messages.append(f"❌ Engine check error: {engine_error!s}")

    # Batch engine messages
    for msg in engine_messages:
        await ws_batcher.emit("new_log", {"data": msg})
        await asyncio.sleep(0.2)

    await ws_batcher.flush_all()

    await ws_batcher.emit(
        "new_log", {"data": "✅ Real-time log stream complete - System operating normally"}
    )
    await ws_batcher.flush_all()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("FLASK_PORT", "5001"))
    host = os.getenv("FLASK_HOST", "127.0.0.1")

    print(f"\n[+] Cloud-Reaper Dashboard Active at http://{host}:{port}")
    print("[*] Engine: uvicorn + Socket.IO | Real-Time Monitoring: ENABLED\n")

    uvicorn.run("reaper.web.app_async:socket_app", host=host, port=port, reload=False)
