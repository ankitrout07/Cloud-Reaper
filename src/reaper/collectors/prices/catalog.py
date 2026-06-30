from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from reaper.collectors.prices.aws import AWSPriceClient
from reaper.collectors.prices.azure import AZURE_RETAIL_SERVICE_NAMES, AzurePriceClient
from reaper.collectors.prices.gcp import GCPPriceClient

logger = logging.getLogger(__name__)

CATALOG_CACHE_TTL_SECONDS = 3600
PROVIDERS = ("azure", "aws", "gcp")

_CATALOG_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_LOCK = threading.Lock()
_FETCH_LOCKS: dict[str, threading.Lock] = {}
_WARM_STATUS: dict[str, str] = dict.fromkeys(PROVIDERS, "idle")
_WARM_META: dict[str, dict[str, Any]] = {}


@dataclass
class CatalogQueryParams:
    """Parameters for querying the price catalog."""

    provider: str
    page: int = 1
    per_page: int = 50
    search: str = ""
    service: str = ""
    region: str = ""
    sort_by: str = "sku-asc"


def normalize_price_record(raw: dict[str, Any], provider: str) -> dict[str, Any] | None:
    """Map provider-specific price payloads to the catalog UI schema."""
    if raw.get("error") or raw.get("reservationTerm"):
        return None

    sku = (
        raw.get("sku")
        or raw.get("armSkuName")
        or raw.get("skuName")
        or raw.get("armResourceName")
        or raw.get("name")
    )
    if not sku:
        return None

    region = raw.get("region") or raw.get("armRegionName") or raw.get("location") or "global"
    service = raw.get("service") or raw.get("serviceName") or raw.get("product_name") or "Compute"

    price = raw.get("price") or raw.get("retailPrice") or raw.get("rate") or raw.get("hourly_price")
    if price is None:
        return None

    try:
        hourly = float(price)
    except (TypeError, ValueError):
        return None

    if hourly <= 0:
        return None

    unit = raw.get("unitOfMeasure", "1 Hour")
    if "Month" in unit:
        hourly = hourly / 730

    description = raw.get("description") or raw.get("productName") or raw.get("meterName") or ""

    # Extract specifications if available
    specifications = {
        "vcpu": raw.get("vcpu"),
        "memory": raw.get("memory"),
        "gpu": raw.get("gpu"),
        "network_performance": raw.get("network_performance"),
        "physical_processor": raw.get("physical_processor"),
        "clock_speed_ghz": raw.get("clock_speed_ghz"),
        "architecture": raw.get("architecture"),
        "instance_family": raw.get("instance_family"),
        "series": raw.get("series"),
        "guestAccelerators": raw.get("guestAccelerators"),
        "machineType": raw.get("machineType"),
        "cpuPlatform": raw.get("cpuPlatform"),
        "storage_type": raw.get("storage_type"),
        "engine": raw.get("engine"),
        "cache_engine": raw.get("cache_engine"),
        "accelerator_type": raw.get("accelerator_type"),
        "tier": raw.get("tier"),
        "type": raw.get("type"),
        "productName": raw.get("productName"),
        "meterName": raw.get("meterName"),
    }

    return {
        "sku": sku,
        "name": sku,
        "service": service,
        "region": region,
        "price": hourly,
        "rate": hourly,
        "hourly_price": hourly,
        "monthly_price": hourly * 730,
        "description": description,
        "provider": provider,
        "specifications": specifications,
    }


def _dedupe_prices(prices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for price in prices:
        key = (price["sku"], price["region"], price["service"])
        existing = seen.get(key)
        if existing is None or price["price"] < existing["price"]:
            seen[key] = price
    return list(seen.values())


def _price_source(provider: str) -> str:
    sources = {
        "azure": "Azure Retail Prices API",
        "aws": "ec2instances.info",
        "gcp": "gcpinstances.info",
    }
    return sources.get(provider, "live API")


def _fetch_provider_raw_prices(provider: str) -> list[dict[str, Any]]:
    if provider == "azure":
        return AzurePriceClient().get_catalog_prices()
    if provider == "aws":
        return AWSPriceClient().get_catalog_prices()
    if provider == "gcp":
        return GCPPriceClient().get_catalog_prices()
    return []


def _build_catalog(provider: str) -> list[dict[str, Any]]:
    raw_prices = _fetch_provider_raw_prices(provider)
    normalized = []
    for raw in raw_prices:
        entry = normalize_price_record(raw, provider)
        if entry:
            normalized.append(entry)
    return _dedupe_prices(normalized)


def _get_cached_catalog(cache_key: str, fetch_fn):
    now = time.time()
    with _CACHE_LOCK:
        if cache_key in _CATALOG_CACHE:
            timestamp, data = _CATALOG_CACHE[cache_key]
            if now - timestamp < CATALOG_CACHE_TTL_SECONDS:
                return data
        if cache_key not in _FETCH_LOCKS:
            _FETCH_LOCKS[cache_key] = threading.Lock()
        fetch_lock = _FETCH_LOCKS[cache_key]

    with fetch_lock:
        now = time.time()
        with _CACHE_LOCK:
            if cache_key in _CATALOG_CACHE:
                timestamp, data = _CATALOG_CACHE[cache_key]
                if now - timestamp < CATALOG_CACHE_TTL_SECONDS:
                    return data

        data = fetch_fn()
        with _CACHE_LOCK:
            _CATALOG_CACHE[cache_key] = (now, data)
        return data


def warm_catalog(provider: str, *, force: bool = False) -> None:
    """Fetch and cache live prices for a single provider."""
    provider = provider.lower()
    if provider not in PROVIDERS:
        return

    with _CACHE_LOCK:
        if _WARM_STATUS.get(provider) == "warming" and not force:
            return
        _WARM_STATUS[provider] = "warming"

    started = time.time()
    try:
        if force:
            with _CACHE_LOCK:
                _CATALOG_CACHE.pop(f"price_catalog_{provider}", None)

        prices = _build_catalog(provider)
        now = time.time()
        with _CACHE_LOCK:
            _CATALOG_CACHE[f"price_catalog_{provider}"] = (now, prices)
            _WARM_STATUS[provider] = "ready"
            _WARM_META[provider] = {
                "count": len(prices),
                "cached_at": now,
                "source": _price_source(provider),
                "warm_seconds": round(now - started, 2),
            }
        logger.info(
            "Price catalog warmed for %s: %s SKUs in %.1fs",
            provider,
            len(prices),
            now - started,
        )
    except Exception as exc:
        with _CACHE_LOCK:
            _WARM_STATUS[provider] = "error"
            _WARM_META[provider] = {
                "error": str(exc),
                "source": _price_source(provider),
            }
        logger.error("Price catalog warm failed for %s: %s", provider, exc)


def warm_all_catalogs(*, force: bool = False) -> None:
    """Warm all provider catalogs in parallel (GCP finishes first)."""
    threads = [
        threading.Thread(
            target=warm_catalog, args=(provider,), kwargs={"force": force}, daemon=True
        )
        for provider in ("gcp", "aws", "azure")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def start_catalog_warmup() -> None:
    """Kick off background warmup for all providers."""
    thread = threading.Thread(target=warm_all_catalogs, kwargs={"force": False}, daemon=True)
    thread.start()


def get_catalog_status(provider: str | None = None) -> dict[str, Any]:
    """Return warmup/cache status for one or all providers."""
    if provider:
        provider = provider.lower()
        with _CACHE_LOCK:
            status = _WARM_STATUS.get(provider, "idle")
            meta = dict(_WARM_META.get(provider, {}))
            cached = _CATALOG_CACHE.get(f"price_catalog_{provider}")
        if cached:
            meta["cache_age_seconds"] = round(time.time() - cached[0], 1)
        return {"provider": provider, "status": status, **meta}

    return {p: get_catalog_status(p) for p in PROVIDERS}


def get_catalog_prices(provider: str) -> list[dict[str, Any]]:
    """Fetch and normalize all catalog prices for a provider, with in-memory caching."""
    provider = provider.lower()

    def fetch():
        return _build_catalog(provider)

    return _get_cached_catalog(f"price_catalog_{provider}", fetch)


def lookup_price(provider: str, sku: str, region: str) -> float | None:
    """Targeted SKU+region price lookup for FinOps cost resolution."""
    provider = provider.lower()
    if provider == "azure":
        client = AzurePriceClient()
        query = (
            f"armSkuName eq '{sku}' and armRegionName eq '{region}' and priceType eq 'Consumption'"
        )
        results = client.get_prices(filter_query=query, max_pages=1)
        if not results:
            return None
        best = next((r for r in results if not r.get("reservationTerm")), results[0])
        entry = normalize_price_record(best, provider)
        return entry["hourly_price"] if entry else None

    if provider == "aws":
        return AWSPriceClient().lookup_price(sku, region)

    if provider == "gcp":
        return GCPPriceClient().lookup_price(sku, region)

    return None


def query_catalog_prices(params: CatalogQueryParams) -> dict[str, Any]:
    """Return a paginated, optionally filtered slice of the cached catalog."""
    provider = params.provider.lower()
    status = get_catalog_status(provider)

    if status["status"] == "warming" and status.get("count", 0) == 0:
        cached = _CATALOG_CACHE.get(f"price_catalog_{provider}")
        if not cached:
            return {
                "prices": [],
                "total": 0,
                "page": params.page,
                "per_page": params.per_page,
                "total_pages": 0,
                "catalog_status": "warming",
                "source": status.get("source"),
            }

    prices = get_catalog_prices(provider)

    if params.search:
        term = params.search.lower()
        prices = [
            p
            for p in prices
            if term in p["sku"].lower()
            or term in p["region"].lower()
            or term in p["service"].lower()
            or term in p.get("description", "").lower()
        ]

    if params.service:
        service_term = params.service.lower()
        prices = [p for p in prices if p["service"].lower() == service_term]

    if params.region:
        region_term = params.region.lower()
        prices = [p for p in prices if p["region"].lower() == region_term]

    if params.sort_by == "price-asc":
        prices.sort(key=lambda p: p["price"])
    elif params.sort_by == "price-desc":
        prices.sort(key=lambda p: p["price"], reverse=True)
    elif params.sort_by == "sku-desc":
        prices.sort(key=lambda p: p["sku"].lower(), reverse=True)
    elif params.sort_by == "region-asc":
        prices.sort(key=lambda p: p["region"].lower())
    elif params.sort_by == "region-desc":
        prices.sort(key=lambda p: p["region"].lower(), reverse=True)
    else:
        prices.sort(key=lambda p: p["sku"].lower())

    total = len(prices)
    page = max(1, params.page)
    per_page = max(1, min(params.per_page, 100))
    start = (page - 1) * per_page
    end = start + per_page

    meta = get_catalog_status(provider)
    return {
        "prices": prices[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page) if total else 0,
        "catalog_status": meta.get("status", "ready"),
        "source": meta.get("source"),
        "sku_count": meta.get("count", total),
        "cached_at": meta.get("cached_at"),
    }


def get_catalog_filters(provider: str) -> dict[str, list[str]]:
    """Distinct service and region values for filter dropdowns."""
    prices = get_catalog_prices(provider)
    if provider.lower() == "azure":
        services = AZURE_RETAIL_SERVICE_NAMES.copy()
    else:
        services = sorted({p["service"] for p in prices})
    regions = sorted({p["region"] for p in prices})
    return {"services": services, "regions": regions}
