from __future__ import annotations

import asyncio
import contextlib
import datetime
import io
import os
import secrets
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from reaper.services.credential_service import get_credential_service
from reaper.utils.error_handler import get_logger

# Try to import Go WebSocket batcher for enhanced performance
try:
    from reaper.integrations.go_websocket import (
        GoWebSocketBatcher,
        emit_cost_alert,
        emit_metric_update,
        emit_resource_update,
        get_websocket_batcher,
    )

    GO_WEBSOCKET_AVAILABLE = True
except ImportError:
    GO_WEBSOCKET_AVAILABLE = False

# Try to import Go rate limiter for enhanced performance
try:
    from reaper.integrations.go_ratelimiter import (
        GoRateLimiter,
        allow_ai_request,
        allow_aws_request,
        allow_azure_request,
        allow_gcp_request,
        get_rate_limiter,
        wait_for_rate_limit,
    )

    GO_RATELIMITER_AVAILABLE = True
except ImportError:
    GO_RATELIMITER_AVAILABLE = False

try:
    from weasyprint import HTML
except Exception as e:
    HTML = None
    print(f"[*] WeasyPrint could not be loaded: {e}")

from reaper.collectors.prices.catalog import (
    CatalogQueryParams,
    get_catalog_filters,
    get_catalog_status,
    query_catalog_prices,
    start_catalog_warmup,
    warm_catalog,
)
from reaper.collectors.providers.azure_collector import AzureCollector
from reaper.collectors.utils.auth_check import check_azure_status
from reaper.engine.core.architect import AIArchitectManager, resolve_component_costs
from reaper.engine.core.calculator import CostCalculator
from reaper.engine.core.cost_optimizer import (
    ComprehensiveCostOptimizer,
)
from reaper.engine.core.cost_reporter import AutomatedCostReporter
from reaper.engine.core.logic import RightSizer
from reaper.engine.models.resources import (
    ActionLog,
    BusinessMetric,
    CloudConnection,
    SessionLocal,
    init_db,
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
    """
    Token bucket rate limiter for API calls.
    Now supports both Python implementation and Go backend for enhanced performance.
    """

    def __init__(
        self,
        rate: int,
        per: float = 1.0,
        use_go_backend: bool = True,
        limiter_key: str | None = None,
    ):
        self.rate = rate  # requests per second
        self.per = per  # time window in seconds
        self.allowance = rate
        self.last_check = time.time()
        self.limiter_key = limiter_key

        # Try to use Go backend if available and enabled
        self.use_go_backend = use_go_backend and GO_RATELIMITER_AVAILABLE
        self.go_limiter: GoRateLimiter | None = None

        if self.use_go_backend:
            try:
                # Don't initialize immediately, will be done lazily
                print(
                    f"[Go Rate Limiter] Using Go backend for enhanced performance (key: {limiter_key})"
                )
            except Exception as e:
                print(f"[Go Rate Limiter] Failed to initialize Go backend: {e}")
                self.use_go_backend = False
                self.go_limiter = None

    def can_proceed(self) -> bool:
        """Check if request can proceed under rate limit (synchronous version)."""
        current = time.time()
        time_passed = current - self.last_check
        self.last_check = current
        self.allowance += time_passed * (self.rate / self.per)

        self.allowance = min(self.allowance, self.rate)

        if self.allowance < 1.0:
            return False
        self.allowance -= 1.0
        return True

    async def can_proceed_async(self) -> bool:
        """Check if request can proceed under rate limit (async version with Go backend support)."""
        # Try to use Go backend if available
        if self.use_go_backend:
            try:
                if self.go_limiter is None:
                    self.go_limiter = await get_rate_limiter()

                allowed = await self.go_limiter.allow(self.limiter_key)
                if allowed:
                    return True
                print(
                    f"[Go Rate Limiter] Request blocked by rate limiter (key: {self.limiter_key})"
                )
                return False
            except (ConnectionError, TimeoutError) as e:
                print(
                    f"[Go Rate Limiter] Connection error checking rate limit: {e}, falling back to Python"
                )
            except (ImportError, AttributeError) as e:
                print(f"[Go Rate Limiter] Go backend not available: {e}, falling back to Python")
            except Exception as e:
                print(
                    f"[Go Rate Limiter] Unexpected error checking rate limit: {e}, falling back to Python"
                )

        # Fall back to Python implementation
        return self.can_proceed()

    async def wait(self):
        """Wait until rate limit allows proceeding."""
        # Try to use Go backend if available
        if self.use_go_backend:
            try:
                if self.go_limiter is None:
                    self.go_limiter = await get_rate_limiter()

                wait_duration = await self.go_limiter.wait(self.limiter_key)
                if wait_duration > 0:
                    await asyncio.sleep(wait_duration / 1000.0)  # Convert ms to seconds
                return
            except (ConnectionError, TimeoutError) as e:
                print(
                    f"[Go Rate Limiter] Connection error waiting for rate limit: {e}, falling back to Python"
                )
            except (ImportError, AttributeError) as e:
                print(f"[Go Rate Limiter] Go backend not available: {e}, falling back to Python")
            except Exception as e:
                print(
                    f"[Go Rate Limiter] Unexpected error waiting for rate limit: {e}, falling back to Python"
                )

        # Fall back to Python implementation
        while not self.can_proceed():
            await asyncio.sleep(0.1)


# Rate limiters for different API providers
azure_rate_limiter = RateLimiter(
    rate=20, per=1.0, use_go_backend=True, limiter_key="azure"
)  # 20 requests per second for Azure
aws_rate_limiter = RateLimiter(
    rate=20, per=1.0, use_go_backend=True, limiter_key="aws"
)  # 20 requests per second for AWS
gcp_rate_limiter = RateLimiter(
    rate=20, per=1.0, use_go_backend=True, limiter_key="gcp"
)  # 20 requests per second for GCP
ai_rate_limiter = RateLimiter(
    rate=10, per=1.0, use_go_backend=True, limiter_key="ai"
)  # 10 requests per second for AI APIs


# WebSocket Message Batching System
class WebSocketBatcher:
    """
    Batches WebSocket messages to reduce network overhead and improve performance.
    Now supports both Python asyncio and Go-based batching for enhanced performance.
    """

    def __init__(
        self, socketio_server, batch_interval_ms=100, max_batch_size=50, use_go_backend=True
    ):
        self.sio = socketio_server
        self.batch_interval = batch_interval_ms / 1000.0  # Convert to seconds
        self.max_batch_size = max_batch_size
        self.batches = {}  # event_name -> list of messages
        self.timers = {}  # event_name -> timer handle
        self.lock = asyncio.Lock()

        # Try to use Go backend if available and enabled
        self.use_go_backend = use_go_backend and GO_WEBSOCKET_AVAILABLE
        self.go_batcher: GoWebSocketBatcher | None = None
        self.websocket_host = "localhost"  # Default host
        self.websocket_port = 7072  # Default port

        if self.use_go_backend:
            try:
                # Get Go WebSocket batcher host/port from environment or use defaults
                self.websocket_host = os.getenv("GO_WEBSOCKET_HOST", "localhost")
                self.websocket_port = int(os.getenv("GO_WEBSOCKET_PORT", "7072"))
                # Don't initialize immediately, will be done lazily
                print(f"[Go WebSocket Batcher] Using Go backend at {self.websocket_host}:{self.websocket_port}")
            except (ValueError, TypeError) as e:
                print(f"[Go WebSocket Batcher] Invalid configuration: {e}, falling back to Python")
                self.use_go_backend = False
                self.go_batcher = None
            except Exception as e:
                print(
                    f"[Go WebSocket Batcher] Unexpected error initializing: {e}, falling back to Python"
                )

    async def emit(self, event: str, data: dict, room: str | None = None):
        """Queue a message for batched emission."""
        # Try to use Go backend if available
        if self.use_go_backend:
            try:
                if self.go_batcher is None:
                    self.go_batcher = await get_websocket_batcher()

                success = await self.go_batcher.emit(event, data, room)
                if success:
                    return  # Successfully sent to Go backend
                print(
                    "[Go WebSocket Batcher] Failed to emit via Go backend, falling back to Python"
                )
            except (ConnectionError, TimeoutError) as e:
                print(f"[Go WebSocket Batcher] Connection error: {e}, falling back to Python")
            except (ImportError, AttributeError) as e:
                print(
                    f"[Go WebSocket Batcher] Go backend not available: {e}, falling back to Python"
                )
            except Exception as e:
                print(f"[Go WebSocket Batcher] Unexpected error: {e}, falling back to Python")

        # Fall back to Python implementation
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

    async def _schedule_flush(self, event: str, room: str | None = None):
        """Schedule batch flush after interval."""
        await asyncio.sleep(self.batch_interval)
        await self._flush_batch(event, room)

    async def _flush_batch(self, event: str, room: str | None = None):
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
ws_batcher = WebSocketBatcher(sio, batch_interval_ms=150, max_batch_size=30, use_go_backend=True)


from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from starlette.requests import Request as StarletteRequest


def jsonify(*args, **kwargs):
    content = args[0] if args and isinstance(args[0], dict) else kwargs
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
from reaper.integrations import go_bridge  # async Go engine bridge (non-blocking)

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
            except (ConnectionError, TimeoutError) as e:
                error_count += 1
                print(f"[!] Metrics Worker Connection Error ({error_count}/{max_errors}): {e}")
                # Exponential backoff for consecutive errors
                if error_count >= max_errors:
                    backoff_time = min(backoff_time * 2, max_backoff)
                    print(
                        f"[!] Too many consecutive connection errors, backing off for {backoff_time} seconds"
                    )
                    error_count = 0
            except (ValueError, TypeError) as e:
                error_count += 1
                print(f"[!] Metrics Worker Data Error ({error_count}/{max_errors}): {e}")
                # Data errors don't need backoff, just skip this iteration
            except Exception as e:
                error_count += 1
                print(f"[!] Metrics Worker Unexpected Error ({error_count}/{max_errors}): {e}")
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
                except (ConnectionError, TimeoutError) as e:
                    print(f"[!] Metrics emit connection error: {e}")
                except Exception as e:
                    print(f"[!] Metrics emit error: {e}")

        except asyncio.CancelledError:
            print("[!] Metrics worker cancelled")
            raise  # Re-raise to allow proper cleanup
        except Exception as e:
            print(f"[!] Critical error in metrics worker: {e}")
            # Prevent rapid crash loops by sleeping longer on critical errors
            backoff_time = min(backoff_time * 2, max_backoff)
            await asyncio.sleep(backoff_time)





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
    # Initialize global credential service
    credential_service = get_credential_service()
    logger = get_logger(__name__)
    logger.info(
        f"Credential service initialized with providers: {list(credential_service.get_all_providers().keys())}"
    )

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
    if user_name and sub_name and timestamp and time.time() - float(timestamp) < cache_ttl:
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














@app.get("/settings")
async def settings(request: Request):
    # Lazy import to avoid circular dependencies
    from reaper.web.routers.settings import _cloud_connections_summary
    from reaper.web.routers.vault import _vault_settings_row
    
    cloud_summary, active_provider = await asyncio.to_thread(_cloud_connections_summary)
    vault_configured = await asyncio.to_thread(_vault_settings_row) is not None
    return render_template(
        "pages/settings.html",
        request=request,
        cloud_connections=cloud_summary,
        active_provider=active_provider,
        vault_configured=vault_configured,
    )
































@app.get("/api/context/switch")
async def switch_context(request: Request):
    provider = (request.query_params.get("provider") or "").lower()
    if provider not in {"aws", "azure", "gcp", "k8s"}:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Unsupported provider."}
        )

    def _do_switch():
        db = SessionLocal()
        try:
            conn = (
                db.query(CloudConnection)
                .filter_by(provider_type=provider)
                .order_by(CloudConnection.updated_at.desc())
                .first()
            )
            if not conn:
                return None, None  # Signal: redirect needed
            db.query(CloudConnection).filter_by(provider_type=provider).update({"is_active": False})
            conn.is_active = True
            db.commit()
            return provider, conn.credentials
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        active_provider, credentials = await asyncio.to_thread(_do_switch)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    if active_provider is None:
        return jsonify(
            {
                "status": "redirect",
                "url": url_for("settings", tab="cloud", provider=provider),
            }
        )

    _set_cloud_env(provider, credentials)
    return jsonify(
        {
            "status": "success",
            "provider": provider,
            "message": f"{provider.upper()} context activated.",
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

    # Offload DB query to thread so the event loop stays free
    def _fetch_metrics():
        db = SessionLocal()
        try:
            return db.query(BusinessMetric).order_by(BusinessMetric.date.desc()).all()
        except Exception:
            return []
        finally:
            db.close()

    db_metrics = await asyncio.to_thread(_fetch_metrics)

    return render_template(
        "pages/financial.html",
        request=request,
        active_tab=tab,
        settings=settings_state,
        db_metrics=db_metrics,
    )










@app.get("/api/metrics")
async def get_dashboard_metrics(request: Request):
    """Provides real metrics from cloud providers or returns empty structure if not configured"""
    if is_first_run():
        return jsonify(
            {
                "status": "unconfigured",
                "message": "Cloud credentials not configured",
                "burn_rate_velocity": 0.00,
                "efficiency_score": 0.0,
                "telemetry_stream": [],
            }
        )

    try:

        def _get_real_metrics():
            c = AzureCollector()
            # Fetch real metrics if available
            try:
                idle_vms = c.get_idle_vms(cpu_threshold=5.0)
                vm_inventory = c.get_vm_inventory()
                total_vms = len(vm_inventory) if vm_inventory else 0
                idle_count = len(idle_vms) if idle_vms else 0

                if total_vms > 0:
                    efficiency_score = ((total_vms - idle_count) / total_vms) * 100
                else:
                    efficiency_score = 100.0

                burn_data = c.get_burn_rate_forecast()
                burn_rate = burn_data.get("burn_rate", 0.0)

                return {
                    "status": "healthy",
                    "burn_rate_velocity": burn_rate,
                    "efficiency_score": efficiency_score,
                    "telemetry_stream": [],
                }
            except Exception as e:
                print(f"[!] Error fetching real metrics: {e}")
                return {
                    "status": "error",
                    "message": str(e),
                    "burn_rate_velocity": 0.00,
                    "efficiency_score": 0.0,
                    "telemetry_stream": [],
                }

        metrics = await asyncio.to_thread(_get_real_metrics)
        return jsonify(metrics)
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "message": str(e),
                "burn_rate_velocity": 0.00,
                "efficiency_score": 0.0,
                "telemetry_stream": [],
            }
        )


# ========== FINANCIAL INTELLIGENCE API ENDPOINTS ==========
































@app.get("/build-with-ai")
async def build_with_ai(request: Request):
    """Renders the AI Multi-Cloud Architect Estimator workspace dashboard."""
    return templates.TemplateResponse(request, "pages/build_with_ai.html", {"request": request})


@app.get("/api/v1/architect/status")
async def api_architect_status(request: Request):
    """Returns the validation state of the configured OpenAI, Gemini, and Claude API keys."""
    # verify_api_status makes blocking HTTP requests — run in a thread
    status = await asyncio.to_thread(architect_manager.verify_api_status)
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
        # Both calls are synchronous (blocking HTTP + CPU work) — offload to thread pool
        def _run_estimate():
            bp = architect_manager.generate_blueprint(
                user_prompt, provider, model_provider=model_provider
            )
            return resolve_component_costs(bp, provider, region)

        calculated_payload = await asyncio.to_thread(_run_estimate)

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


@app.get("/visualizer")
async def visualizer(request: Request):
    """Infrastructure Topology Visualizer — renders a Cytoscape.js directed graph
    of all cloud resources pulled in real-time from the Go Engine bridge.
    """
    return templates.TemplateResponse(request, "pages/visualizer.html", {"request": request})


@app.get("/dashboard")
async def dashboard(request: Request):
    user_name, sub_name = await _get_cached_user_info(request)
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
async def api_dashboard_finops_charts(request: Request, resource_group: Optional[str] = None):
    """HTTP snapshot for heavier FinOps charts (refreshed periodically from the client)."""
    if is_first_run():
        return JSONResponse(status_code=200, content={"status": "unconfigured", "charts": None})

    cache_key = "finops_charts_data"
    if resource_group:
        cache_key += f"_{resource_group}"
        
    cache_ttl = 60  # 60 seconds cache for chart data

    # Check session cache first
    cached_charts = request.session.get(cache_key)
    cached_timestamp = request.session.get(f"{cache_key}_timestamp")

    # Return cached data if valid
    if cached_charts and cached_timestamp and time.time() - float(cached_timestamp) < cache_ttl:
        return {"status": "ok", "charts": cached_charts, "cached": True}

    try:

        def _fetch_charts():
            c = AzureCollector()
            budget = float(settings_state.get("budget_threshold", 1000.0))
            return c.get_finops_dashboard_snapshot(monthly_budget=budget, resource_group=resource_group)

        charts = await asyncio.to_thread(_fetch_charts)

        # Cache in session
        request.session[cache_key] = charts
        request.session[f"{cache_key}_timestamp"] = str(time.time())

        return {"status": "ok", "charts": charts, "cached": False}
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e), "charts": None}
        )


@app.get("/api/dashboard/scopes")
async def api_dashboard_scopes(request: Request):
    """Returns available resource scopes (projects/resource groups) for the context switcher."""
    if is_first_run():
        return JSONResponse(status_code=200, content={"status": "unconfigured", "scopes": []})

    cache_key = "dashboard_scopes"
    cache_ttl = 300  # 5 minutes cache

    cached_scopes = request.session.get(cache_key)
    cached_timestamp = request.session.get(f"{cache_key}_timestamp")

    if cached_scopes and cached_timestamp and time.time() - float(cached_timestamp) < cache_ttl:
        return {"status": "ok", "scopes": cached_scopes, "cached": True}

    try:
        def _fetch_scopes():
            c = AzureCollector()
            return c.get_resource_groups()

        scopes = await asyncio.to_thread(_fetch_scopes)

        request.session[cache_key] = scopes
        request.session[f"{cache_key}_timestamp"] = str(time.time())

        return {"status": "ok", "scopes": scopes, "cached": False}
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e), "scopes": []}
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
        params = CatalogQueryParams(
            provider=provider,
            page=page,
            per_page=per_page,
            search=search,
            service=service,
            region=region,
            sort_by=sort_by,
        )
        result = query_catalog_prices(params)
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
        if request.headers.get("content-type", "").startswith("application/json")
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




@app.get("/api/activity")
async def get_activity(request: Request):
    try:
        def _fetch_activity():
            session = SessionLocal()
            try:
                logs = session.query(ActionLog).order_by(ActionLog.timestamp.desc()).limit(10).all()
                return [
                    {
                        "resource": log.resource.name if log.resource else "Unknown",
                        "action": log.action_type,
                        "status": log.status,
                        "time": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    for log in logs
                ]
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        result = await asyncio.to_thread(_fetch_activity)
        return {"status": "success", "activity": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})












# Initialize the comprehensive cost optimizer
cost_optimizer = ComprehensiveCostOptimizer()

# Initialize the automated cost reporter
cost_reporter = AutomatedCostReporter()














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

# Injected router includes
from reaper.web.routers.cost_optimization import router as cost_optimization_router
from reaper.web.routers.financial import router as financial_router
from reaper.web.routers.finops import router as finops_router
from reaper.web.routers.resources import router as resources_router
from reaper.web.routers.settings import router as settings_router
from reaper.web.routers.vault import router as vault_router

app.include_router(settings_router)
app.include_router(vault_router)
app.include_router(financial_router)
app.include_router(finops_router)
app.include_router(resources_router)
app.include_router(cost_optimization_router)

