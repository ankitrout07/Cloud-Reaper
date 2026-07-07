# src/reaper/web/metrics_router.py
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from reaper.engine.models.resources import Resource, SessionLocal
from reaper.engine.notifications.notifier import send_discord_alert, send_slack_alert
from reaper.engine.telemetry.metrics_analyzer import FinOpsTelemetryAnalyzer

telemetry_router = APIRouter()
# Points to internal standard Prometheus routing endpoints
analyzer = FinOpsTelemetryAnalyzer(prometheus_url="http://localhost:9090")


@telemetry_router.post("/api/v1/finops/telemetry-insights")
async def get_telemetry_driven_insights():
    # Offload blocking SQLAlchemy query to thread pool
    def _fetch_inventory():
        db = SessionLocal()
        try:
            resources = db.query(Resource).filter(Resource.active).all()
            return [
                {
                    "resource_id": r.id,
                    "private_ip": (r.tags or {}).get("private_ip") or "",
                    "sku_size": (r.tags or {}).get("sku_size") or r.type or "Unknown",
                    "monthly_cost": float((r.tags or {}).get("monthly_cost", 0.0)),
                }
                for r in resources
            ]
        finally:
            db.close()

    try:
        db_inventory = await asyncio.to_thread(_fetch_inventory)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Database fetch failure: {e!s}"},
        )

    try:
        actionable_insights = analyzer.analyze_compute_waste_index(db_inventory)
        return {
            "status": "success",
            "telemetry_source": "Prometheus v1 Engine",
            "recommendations": actionable_insights,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Telemetry parsing failure: {e!s}"},
        )


@telemetry_router.post("/api/v1/finops/test-webhook")
async def test_alert_webhook(payload: dict[str, Any] | None = None):
    data = payload or {}
    platform = data.get("platform", "").lower()
    webhook_url = data.get("webhook_url", "").strip()

    if not webhook_url:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Webhook URL is required"},
        )

    # Standard security validation
    if not webhook_url.startswith("http://") and not webhook_url.startswith("https://"):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Invalid webhook URL format"},
        )

    try:
        success = False
        if platform == "discord" or "discord.com" in webhook_url:
            # send_discord_alert calls requests.post — offload to thread
            success = await asyncio.to_thread(
                send_discord_alert,
                title="🔔 Cloud-Reaper Webhook Active",
                message="Your Discord notification channel has been successfully verified!",
                color=0x00F3FF,
                webhook_url=webhook_url,
            )
        elif platform == "slack" or "slack.com" in webhook_url:
            # send_slack_alert calls requests.post — offload to thread
            success = await asyncio.to_thread(
                send_slack_alert,
                message="🔔 *Cloud-Reaper Webhook Active*\nYour Slack notification channel has been successfully verified!",
                webhook_url=webhook_url,
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Unrecognized or unsupported webhook platform",
                },
            )

        if success:
            return {"status": "success", "message": "Test notification sent successfully!"}

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Test notification failed. Please verify the URL.",
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Alert dispatch failure: {e!s}"},
        )
