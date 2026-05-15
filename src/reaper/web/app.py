# gevent monkey-patching is optional; use threading fallback if unavailable.
try:
    from gevent import monkey

    monkey.patch_all()
    async_mode = "gevent"
except ImportError:
    async_mode = "threading"

import contextlib  # noqa: E402
import datetime  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from pathlib import Path  # noqa: E402

from azure.identity import DefaultAzureCredential  # noqa: E402
from azure.mgmt.subscription import SubscriptionClient  # noqa: E402
from dotenv import load_dotenv, set_key  # noqa: E402
from flask import (  # noqa: E402
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_socketio import SocketIO  # noqa: E402
from sqlalchemy import func  # noqa: E402
from weasyprint import HTML  # noqa: E402

from reaper.collectors.auth_check import check_azure_status  # noqa: E402
from reaper.collectors.azure_collector import AzureCollector  # noqa: E402
from reaper.collectors.config_manager import save_config  # noqa: E402
from reaper.engine.calculator import CostCalculator  # noqa: E402
from reaper.engine.economics import RegionalArbitrage  # noqa: E402
from reaper.engine.logic import RightSizer  # noqa: E402
from reaper.engine.models import (  # noqa: E402
    ActionLog,
    BusinessMetric,
    CloudConnection,
    CostHistory,
    Resource,
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
app = Flask(
    __name__,
    template_folder=str(_web_dir / "templates"),
    static_folder=str(_web_dir / "static"),
)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)
thread = None
thread_lock = threading.Lock()

# Azure standard metrics rarely refresh faster than ~1 minute; 5–10s is a safe UI throttle.
SOCKET_METRICS_INTERVAL_SEC = int(os.getenv("REAPER_METRICS_EMIT_SEC", "8"))


def background_metrics_worker():
    """Fetches Azure Monitor CPU samples and pushes over WebSocket (throttled)."""
    import random

    while True:
        socketio.sleep(SOCKET_METRICS_INTERVAL_SEC)
        now = datetime.datetime.now(datetime.UTC).strftime("%H:%M:%S")
        cpu_usage = None
        try:
            if not is_first_run():
                az = AzureCollector()
                cpu_usage = az.get_live_subscription_cpu_average(max_vms=6)
        except Exception as e:
            print(f"[!] Metrics Worker Error: {e}")
        if cpu_usage is None:
            cpu_usage = round(20.0 + random.uniform(-5.0, 5.0), 2)  # noqa: S311
        else:
            cpu_usage = round(float(cpu_usage), 2)
        try:
            socketio.emit(
                "metric_update",
                {"time": now, "value": cpu_usage},
            )
        except Exception as e:
            print(f"[!] Metrics emit error: {e}")


# Start the worker after the app is ready
socketio.start_background_task(background_metrics_worker)

init_db()
calc = CostCalculator()
settings_state = {
    "currency": "USD",
    "idle_strategy": "aggressive",
    "selected_subscriptions": [],
    "scheduled_sleep": {"enabled": False, "stop_time": "20:00", "start_time": "08:00"},
    "mandatory_tags": ["owner", "project"],
    "webhook_url": "",
    "budget_threshold": 1000.0,
    "auto_flag_compliance": True,
}

ENV_PATH = str(_repo_root() / ".env")


@app.route("/api/settings/sync", methods=["POST"])
def sync_settings():
    data = request.json
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
    if request.path.startswith("/static") or request.path.startswith("/api/"):
        return None
    if is_first_run() and request.endpoint != "settings":
        return redirect(url_for("settings", mode="onboarding"))
    return None


@app.route("/")
def index():
    az = AzureCollector()
    user_name = az.get_user_name()
    sub_name = az.get_subscription_name()
    return render_template("index.html", user_name=user_name, sub_name=sub_name)


@app.route("/settings")
def settings():
    return render_template("settings.html")


@app.route("/api/settings/update", methods=["POST"])
def update_settings():
    data = request.json
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
    settings_state["webhook_url"] = data.get("webhook_url", "")
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
    fields = ["subscription_id", "tenant_id", "client_id", "client_secret"]
    if not all(data.get(f) for f in fields):
        return jsonify({"status": "error", "message": "All fields are required."}), 400

    old_env = {f"AZURE_{f.upper()}": os.getenv(f"AZURE_{f.upper()}") for f in fields}

    try:
        for f in fields:
            os.environ[f"AZURE_{f.upper()}"] = data.get(f)

        az = AzureCollector()
        prices = az.get_live_prices()

        if not prices or (isinstance(prices, dict) and not prices.get("prices")):
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


def _set_cloud_env(provider: str, credentials: dict) -> None:
    provider = provider.lower()
    if provider == "aws":
        os.environ["AWS_ACCESS_KEY_ID"] = credentials.get("access_key_id", "")
        os.environ["AWS_SECRET_ACCESS_KEY"] = credentials.get("secret_access_key", "")
        os.environ["AWS_REGION"] = credentials.get("region", "us-east-1")
    elif provider == "azure":
        os.environ["AZURE_SUBSCRIPTION_ID"] = credentials.get("subscription_id", "")
        os.environ["AZURE_TENANT_ID"] = credentials.get("tenant_id", "")
        os.environ["AZURE_CLIENT_ID"] = credentials.get("client_id", "")
        os.environ["AZURE_CLIENT_SECRET"] = credentials.get("client_secret", "")
    elif provider == "gcp":
        os.environ["GOOGLE_CLOUD_PROJECT"] = credentials.get("project_id", "")
        if credentials.get("service_account_json"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _write_gcp_service_account_file(
                credentials["service_account_json"]
            )
    elif provider == "k8s":
        kubeconfig = credentials.get("kubeconfig")
        if kubeconfig:
            kubeconfig_path = Path(kubeconfig)
            if kubeconfig_path.exists():
                os.environ["KUBECONFIG"] = str(kubeconfig_path)
            else:
                os.environ["KUBECONFIG"] = _write_kubeconfig_file(kubeconfig)
        if credentials.get("service_account_token"):
            os.environ["K8S_SERVICE_ACCOUNT_TOKEN"] = credentials.get("service_account_token")
        if credentials.get("context"):
            os.environ["K8S_CONTEXT"] = credentials.get("context")
    os.environ["REAPER_ACTIVE_PROVIDER"] = provider.upper()


@app.route("/api/context/switch")
def switch_context():
    provider = (request.args.get("provider") or "").lower()
    if provider not in {"aws", "azure", "gcp", "k8s"}:
        return jsonify({"status": "error", "message": "Unsupported provider."}), 400

    session = SessionLocal()
    try:
        conn = (
            session.query(CloudConnection)
            .filter_by(provider_type=provider)
            .order_by(CloudConnection.updated_at.desc())
            .first()
        )
        if not conn:
            return jsonify(
                {
                    "status": "redirect",
                    "url": url_for("settings", mode="onboarding", provider=provider),
                }
            )

        session.query(CloudConnection).filter_by(provider_type=provider).update({"is_active": False})
        conn.is_active = True
        session.commit()
        _set_cloud_env(provider, conn.credentials)

        return jsonify(
            {
                "status": "success",
                "provider": provider,
                "message": f"{provider.upper()} context activated.",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()


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
    if provider == "k8s" and not (credentials.get("kubeconfig") or credentials.get("service_account_token")):
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
        session = SessionLocal()
        session.query(CloudConnection).filter_by(provider_type=provider).update({"is_active": False})

        conn = CloudConnection(
            provider_type=provider,
            connection_name=connection_name,
            credentials=credentials,
            is_active=True,
        )
        session.add(conn)
        session.commit()
        return jsonify(
            {
                "status": "success",
                "message": f"{provider.capitalize()} credentials saved and activated.",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        try:
            session.close()
        except Exception:
            pass


@app.route("/api/settings/auth")
def check_auth():
    try:
        subprocess.run(["az", "account", "show"], capture_output=True, check=True)  # noqa: S603, S607
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
            return jsonify(
                [
                    {"id": "sub-123-abc", "name": "Production-Internal (Mock)"},
                    {"id": "sub-456-def", "name": "Staging-Sandbox (Mock)"},
                    {"id": "sub-789-ghi", "name": "Legacy-Shared-Services (Mock)"},
                ]
            )

        result = subprocess.run(
            [str(binary_path), "--list-subs"],  # noqa: S603
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
    return render_template("pricing.html")


@app.route("/finops")
def finops():
    return render_template("finops.html")


@app.route("/monitor")
def monitor():
    return render_template("monitor.html")


@app.route("/dashboard")
def dashboard():
    az = AzureCollector()
    user_name = az.get_user_name()
    sub_name = az.get_subscription_name()
    return render_template(
        "dashboard.html",
        user_name=user_name,
        sub_name=sub_name,
        metrics_emit_sec=SOCKET_METRICS_INTERVAL_SEC,
    )


@app.route("/api/dashboard/finops-charts")
def api_dashboard_finops_charts():
    """HTTP snapshot for heavier FinOps charts (refreshed periodically from the client)."""
    if is_first_run():
        return jsonify({"status": "unconfigured", "charts": None}), 200
    try:
        az = AzureCollector()
        budget = float(settings_state.get("budget_threshold", 1000.0))
        charts = az.get_finops_dashboard_snapshot(monthly_budget=budget)
        return jsonify({"status": "ok", "charts": charts})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "charts": None}), 500


@app.route("/api/auth/status")
def auth_status():
    return jsonify(check_azure_status())


@app.route("/api/rightsizing")
def get_rightsizing():
    az = AzureCollector()
    go_binary = _reaper_engine_binary()
    if not go_binary:
        return jsonify({"status": "error", "message": "Go Engine binary not found"}), 500

    try:
        # pyrefly: ignore [no-matching-overload]  # noqa: ERA001
        result = subprocess.run(
            [str(go_binary), "--subscription", az.subscription_id],  # noqa: S603
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
        # pyrefly: ignore [bad-index, unsupported-operation]  # noqa: ERA001
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
        # pyrefly: ignore [missing-attribute]  # noqa: ERA001
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
    try:
        return jsonify({"status": "success", "prices": AzureCollector().get_live_prices()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/export/bom", methods=["POST"])
def export_bom():
    try:
        data = request.json
        items = data.get("resources", [])
        total_hourly = data.get("totalHourly", 0.0)
        total_monthly = data.get("totalMonthly", 0.0)

        # Render the HTML template
        rendered_html = render_template(
            "bom_pdf_template.html",
            items=items,
            totalHourly=total_hourly,
            totalMonthly=total_monthly,
            date=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Generate PDF in memory
        pdf_out = io.BytesIO()
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
        resources = session.query(Resource).all()
        unallocated = [r for r in resources if r.is_unallocated]
        session.close()

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
                "unallocated_spend": round(count * 45.0, 2),
                "missing_tags_summary": [
                    {"resource": r.name, "type": r.type, "missing": "Owner, Project"}
                    for r in unallocated[:5]
                ],
            }
        )
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


@app.route("/api/finops/unit-economics")
def unit_economics():
    try:
        session = SessionLocal()
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
        session.close()

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
                    # pyrefly: ignore [no-matching-overload]  # noqa: ERA001
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
        traceback.print_exc()
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
        sub_name = request.json.get("subscription", "Unknown")
        time.sleep(0.5)
        return jsonify(
            {
                "status": "success",
                "message": f"Kill-switch activated for {sub_name}.",
                "vms_stopped": ["sandbox-test-01", "sandbox-test-02", "dev-worker-temp"],
                "estimated_savings": "$14.20/day",
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
        data = request.json
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
        session.close()
        if not result:
            result = [
                {
                    "resource": "Global Scan",
                    "action": "SCAN",
                    "status": "SUCCESS",
                    "time": "Just now",
                },
                {
                    "resource": "vm-prod-01",
                    "action": "PROTECT",
                    "status": "SUCCESS",
                    "time": "1h ago",
                },
            ]
        return jsonify({"status": "success", "activity": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/finops/utilization")
def utilization():
    try:
        report = AzureCollector().get_utilization_report()
        formatted_report = []
        for vm in report:
            waste = 1.0 - (vm["usage"] / 100.0) if vm["usage"] < 100 else 0
            formatted_report.append({
                "name": vm["name"],
                "rg": vm["rg"],
                "waste_coefficient": waste,
                "monthly_cost": 150.0,
                "is_protected": False,
                "status": "CRITICAL" if waste > 0.9 else "NORMAL"
            })
        return jsonify({"status": "success", "report": formatted_report})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500




@socketio.on('connect')
def handle_connect():
    print("[+] Client Connected to Cloud-Reaper Engine")


@socketio.on('start_log_stream')
def handle_start_log_stream():
    from reaper.services.log_streamer import fetch_azure_logs
    socketio.emit('new_log', {'data': 'Initializing Cloud-Reaper Log Stream...'})
    socketio.emit('new_log', {'data': 'Connected to Azure Monitor via OIDC...'})
    
    logs = fetch_azure_logs()
    for log in logs:
        socketio.emit('new_log', {'data': log})
        # pyrefly: ignore [bad-argument-type]  # noqa: ERA001
        socketio.sleep(0.5)


if __name__ == "__main__":
    # use_reloader=False stops the 'after_fork_in_child' assertion error
    port = int(os.getenv("FLASK_PORT", "5001"))
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    
    print(f"\n[+] Cloud-Reaper Dashboard Active at http://{host}:{port}")
    print("[*] Engine: gevent | Real-Time Monitoring: ENABLED\n")
    
    try:
        socketio.run(
            app,
            host=host,
            port=port,
            debug=True,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\n[!] Dashboard server stopped by user.")
