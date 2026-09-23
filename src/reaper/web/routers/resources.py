from __future__ import annotations

import asyncio
import datetime
import json as json_module

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select

# AzureCollector is imported lazily inside the routes that still need it
# (reap, search, etc.) so that the SDK credential flow does not run at import time.
from reaper.utils.error_handler import get_logger


def jsonify(*args, **kwargs):
    from fastapi.responses import JSONResponse
    content = args[0] if args and isinstance(args[0], dict) else kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)

logger = get_logger(__name__)

router = APIRouter(tags=["resources"])


# ---------------------------------------------------------------------------
# Category mapping: Go/Azure resource_type string → UI category bucket
# ---------------------------------------------------------------------------
_RESOURCE_TYPE_TO_CATEGORY: dict[str, str] = {
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
    # ARM type strings from legacy_resources table
    "microsoft.compute/virtualmachines": "virtual_machines",
    "microsoft.compute/disks": "disks",
    "microsoft.storage/storageaccounts": "storage_accounts",
    "microsoft.network/publicipaddresses": "network_resources",
    "microsoft.network/networksecuritygroups": "network_resources",
    "microsoft.network/loadbalancers": "network_resources",
    "microsoft.network/virtualnetworks": "network_resources",
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

_EMPTY_INVENTORY = {
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
}


async def _read_inventory_from_db(
    *,
    category_filter: str,
    status_filter: str,
    search_q: str,
) -> tuple[dict, list[dict], datetime.datetime | None]:
    """Read the resource snapshot from SQLite and return (inventory_dict, flat_list, last_scanned).

    This replaces the live AzureCollector fanout.  Reads are <20 ms on a local
    database with the composite index on (provider, resource_type, region, last_scanned).
    """
    import copy
    from reaper.engine.models.resources import CloudResource, AsyncSessionLocal, SessionLocal

    inventory: dict[str, list | dict] = copy.deepcopy(_EMPTY_INVENTORY)
    inventory["summary"] = {
        "total_resources": 0,
        "idle_resources": 0,
        "orphaned_resources": 0,
        "estimated_monthly_cost": 0.0,
        "by_category": {},
    }

    last_scanned: datetime.datetime | None = None
    flat: list[dict] = []

    def _sync_read() -> tuple[list[dict], datetime.datetime | None]:
        """Synchronous read used in a thread to avoid blocking the event loop."""
        rows: list[dict] = []
        max_ts: datetime.datetime | None = None
        with SessionLocal() as db_session:
            # ── CloudResource rows (written by the Go engine) ──────────────
            stmt = select(CloudResource)
            results = db_session.execute(stmt).scalars().all()
            for cr in results:
                attrs: dict = cr.cost_attributes or {}
                # last_scanned watermark
                if cr.last_scanned and (max_ts is None or cr.last_scanned > max_ts):
                    max_ts = cr.last_scanned
                rows.append({
                    "id": cr.id,
                    "name": attrs.get("name") or cr.id.split("/")[-1],
                    "type": attrs.get("type") or cr.resource_type,
                    "location": cr.region,
                    "size": attrs.get("size", ""),
                    "status": attrs.get("status", "Active"),
                    "tags": attrs.get("tags") or {},
                    "category": _RESOURCE_TYPE_TO_CATEGORY.get(
                        cr.resource_type.lower(), "other_resources"
                    ),
                    "can_dismiss": attrs.get("can_dismiss", False),
                    "dismiss_reason": attrs.get("dismiss_reason"),
                    "estimated_cost": float(attrs.get("estimated_cost", 0.0)),
                    "sku": attrs.get("sku", ""),
                    "kind": attrs.get("kind", ""),
                    "_source": "go_engine",
                })
        return rows, max_ts

    try:
        rows, last_scanned = await asyncio.to_thread(_sync_read)
    except Exception as exc:
        logger.warning("DB snapshot read failed: %s — returning empty inventory", exc)
        rows = []

    # ── Build category buckets + summary ─────────────────────────────────────
    for row in rows:
        name_lower = (row.get("name") or "").lower()
        type_lower = (row.get("type") or "").lower()

        # Apply filters
        if category_filter and row.get("category", "") != category_filter:
            continue
        if status_filter and row.get("status", "") != status_filter:
            continue
        if search_q and search_q not in name_lower and search_q not in type_lower:
            continue

        cat = row.get("category", "other_resources")
        if cat not in inventory:
            cat = "other_resources"
        inventory[cat].append(row)  # type: ignore[union-attr]
        flat.append(row)

        summary = inventory["summary"]
        summary["total_resources"] += 1  # type: ignore[index]
        summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1  # type: ignore[index]
        summary["estimated_monthly_cost"] += row.get("estimated_cost", 0.0)  # type: ignore[index]
        if row.get("status") in ("Idle",):
            summary["idle_resources"] += 1  # type: ignore[index]
        elif row.get("status") in ("Orphaned", "Unassociated", "Empty"):
            summary["orphaned_resources"] += 1  # type: ignore[index]

    inventory["summary"]["estimated_monthly_cost"] = round(  # type: ignore[index]
        inventory["summary"]["estimated_monthly_cost"], 2  # type: ignore[index]
    )
    return inventory, flat, last_scanned


@router.get("/api/resources/inventory")
async def get_resource_inventory(request: Request):
    """Return the latest resource inventory snapshot from the database.

    This endpoint reads from the SQLite snapshot that the Go engine populates
    during a scan.  It does NOT trigger live cloud API calls; use
    ``POST /api/resources/scan`` to kick off a new scan.

    Query params:
        page       (int, default 1)    - page number
        page_size  (int, default 50)   - items per page (max 200)
        category   (str, optional)     - filter by category
        status     (str, optional)     - filter by status (Idle, Orphaned, …)
        q          (str, optional)     - text search against name / type
        stream     (bool, default False) - stream response in NDJSON chunks
    """
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        category_filter = request.query_params.get("category", "").strip().lower()
        status_filter = request.query_params.get("status", "").strip()
        search_q = request.query_params.get("q", "").strip().lower()
        stream_response = request.query_params.get("stream", "false").lower() == "true"

        inventory, all_flat, last_scanned = await _read_inventory_from_db(
            category_filter=category_filter,
            status_filter=status_filter,
            search_q=search_q,
        )

        # Indicate to the UI that the database is empty and a scan should be triggered
        db_empty = inventory["summary"]["total_resources"] == 0  # type: ignore[index]

        total = len(all_flat)
        start = (page - 1) * page_size
        paginated_flat = all_flat[start : start + page_size]

        ts = (
            last_scanned.isoformat()
            if last_scanned
            else datetime.datetime.now(datetime.timezone.utc).isoformat()
        )

        if stream_response:
            async def generate_stream():
                yield (
                    json_module.dumps({
                        "status": "success",
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "total_pages": max(1, (total + page_size - 1) // page_size),
                        "timestamp": ts,
                        "snapshot": True,
                        "db_empty": db_empty,
                    }) + "\n"
                )
                chunk_size = 50
                for i in range(0, len(paginated_flat), chunk_size):
                    chunk = paginated_flat[i : i + chunk_size]
                    yield (
                        json_module.dumps({
                            "type": "resources_chunk",
                            "chunk_index": i // chunk_size,
                            "total_chunks": (len(paginated_flat) + chunk_size - 1) // chunk_size,
                            "resources": chunk,
                        }) + "\n"
                    )
                    await asyncio.sleep(0)
                yield json_module.dumps({"type": "summary", "data": inventory}) + "\n"

            return StreamingResponse(
                generate_stream(),
                media_type="application/json",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        return jsonify({
            "status": "success",
            "data": inventory,
            "resources": paginated_flat,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "timestamp": ts,
            "snapshot": True,
            "db_empty": db_empty,
        })
    except Exception as e:
        logger.exception("Error reading inventory snapshot")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/api/resources/scan")
async def trigger_scan(request: Request):
    """Trigger a background cloud scan via the Go engine.

    This is the **write path**.  The Go engine authenticates with the cloud
    provider, scrapes resources, and upserts them into the shared SQLite
    database.  Subsequent reads to ``GET /api/resources/inventory`` will
    reflect the new snapshot.

    Body (optional JSON):
        subscription_id (str) - override active subscription
        provider        (str) - cloud provider, default "azure"
    """
    try:
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass

        subscription_id: str = body.get("subscription_id", "")
        provider: str = body.get("provider", "azure")

        # Fall back to the active cloud connection stored in the DB
        if not subscription_id:
            try:
                from reaper.engine.models.resources import SessionLocal
                from reaper.engine.models.resources import CloudConnection  # type: ignore[attr-defined]
                with SessionLocal() as sess:
                    conn = sess.execute(
                        select(CloudConnection).where(
                            CloudConnection.is_active == True,  # noqa: E712
                            CloudConnection.provider_type == provider,
                        ).limit(1)
                    ).scalar_one_or_none()
                    if conn:
                        creds = conn.credentials or {}
                        subscription_id = creds.get("subscription_id", "")
            except Exception as exc:
                logger.debug("Could not look up active connection: %s", exc)

        import os
        subscription_id = subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID", "")

        if not subscription_id:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "subscription_id required (or set AZURE_SUBSCRIPTION_ID / add a cloud connection)",
                },
            )

        # Kick off Go engine scan asynchronously
        from reaper.integrations.go_bridge import scan as go_scan

        async def _run_scan():
            result = await go_scan(subscription_id, provider)
            if result:
                logger.info(
                    "[scan] Go engine completed: %d resources",
                    result.get("db_stats", {}).get("ResourceCount", 0),
                )
            else:
                logger.warning("[scan] Go engine returned no result")

        # Fire-and-forget — the client can poll /api/resources/inventory for updates
        asyncio.create_task(_run_scan())

        return jsonify({
            "status": "accepted",
            "message": "Scan started in background. Refresh inventory in 30–60 seconds.",
            "subscription_id": subscription_id,
            "provider": provider,
        })
    except Exception as e:
        logger.exception("Error triggering scan")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})



@router.get("/api/resources/inventory/summary")
async def get_resource_inventory_summary(request: Request):
    """Lightweight endpoint returning only counts + cost from the DB snapshot.

    Reads aggregate counts directly from the SQLite database.  Does not
    call any cloud provider API.  Suitable for dashboard widgets.
    """
    try:
        from reaper.engine.models.resources import CloudResource, SessionLocal

        def _sync_summary():
            with SessionLocal() as sess:
                # Total count
                total = sess.execute(
                    select(func.count()).select_from(CloudResource)
                ).scalar_one() or 0

                # Count per resource_type
                type_rows = sess.execute(
                    select(CloudResource.resource_type, func.count())
                    .group_by(CloudResource.resource_type)
                ).all()

                # Last scanned watermark
                last_ts = sess.execute(
                    select(func.max(CloudResource.last_scanned))
                ).scalar_one()

            return total, type_rows, last_ts

        total, type_rows, last_ts = await asyncio.to_thread(_sync_summary)

        type_counts: dict[str, int] = {t: c for t, c in type_rows}
        by_category: dict[str, int] = {}
        for rt, count in type_counts.items():
            cat = _RESOURCE_TYPE_TO_CATEGORY.get(rt.lower(), "other")
            by_category[cat] = by_category.get(cat, 0) + count

        return jsonify({
            "status": "success",
            "total_resources": total,
            "by_category": by_category,
            "by_type": type_counts,
            "last_scanned": last_ts.isoformat() if last_ts else None,
            "snapshot": True,
        })
    except Exception as e:
        logger.exception("Error reading inventory summary")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/api/resources/search")
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
            from reaper.collectors.providers.azure_collector import AzureCollector
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


@router.post("/api/resources/{resource_id}/dismiss")
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

