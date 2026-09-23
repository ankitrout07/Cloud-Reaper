# src/reaper/integrations/go_bridge.py
#
# Async Go Engine Bridge Client
# ==============================
# This module provides a non-blocking async interface to the Go engine HTTP
# bridge server (`--mode serve`).  It replaces the old pattern of calling
# subprocess.run() synchronously from FastAPI route handlers — which would
# block the entire ASGI event loop until the OS process returns.
#
# Architecture
# ------------
#
#   FastAPI handler (async)
#         │
#         ▼
#   go_bridge.scan()   ◄── awaitable, releases event loop during I/O wait
#         │
#         ▼  httpx AsyncClient (non-blocking TCP)
#   Go bridge :7070
#         │
#         ├─ AzureScraper.ScanResources()
#         └─ db.BatchUpsert()   ◄── sync.Pool zero-alloc path
#
# Fallback
# ---------
# If the bridge server is not running (e.g. binary not built), every call
# automatically falls back to asyncio.create_subprocess_exec() — still
# non-blocking, but with per-call process-fork overhead.
#
# Configuration
# -------------
# REAPER_GO_BRIDGE_PORT  (default 7070)  — port the Go bridge listens on
# REAPER_GO_BRIDGE_TIMEOUT (default 120) — per-request timeout in seconds

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

_BRIDGE_PORT = int(os.getenv("REAPER_GO_BRIDGE_PORT", "7070"))
_BRIDGE_BASE = f"http://127.0.0.1:{_BRIDGE_PORT}"
_TIMEOUT = float(os.getenv("REAPER_GO_BRIDGE_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# Persistent HTTP client — shared across all bridge calls in this process.
# httpx.AsyncClient maintains a connection pool to the Go bridge; opening a
# new client per call (the old pattern) paid TCP handshake overhead on every
# scan/price request and defeated keep-alive.
# ---------------------------------------------------------------------------
_bridge_client: "httpx.AsyncClient | None" = None
_bridge_client_lock: asyncio.Lock | None = None


def _get_bridge_lock() -> asyncio.Lock:
    """Lazily create the lock so it is bound to the running event loop."""
    global _bridge_client_lock
    if _bridge_client_lock is None:
        _bridge_client_lock = asyncio.Lock()
    return _bridge_client_lock


async def _get_bridge_client() -> "httpx.AsyncClient":
    """Return (or create) the module-level persistent httpx client."""
    import httpx

    global _bridge_client
    async with _get_bridge_lock():
        if _bridge_client is None or _bridge_client.is_closed:
            _bridge_client = httpx.AsyncClient(
                timeout=_TIMEOUT,
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                    keepalive_expiry=30,
                ),
            )
    return _bridge_client


def _repo_root() -> Path:
    """
    Get the repository root directory.

    Returns:
        Path to the repository root
    """
    return Path(__file__).resolve().parent.parent.parent.parent


def _engine_binary() -> Path | None:
    """
    Find the Go engine binary.

    Returns:
        Path to the binary if found, None otherwise
    """
    root = _repo_root()
    name = "reaper-engine.exe" if os.name == "nt" else "reaper-engine"
    for candidate in (root / "bin" / name, root / "src" / "engine-go" / name):
        if candidate.is_file():
            return candidate
    return None


async def _is_bridge_alive() -> bool:
    """Quick health check — returns True if the bridge HTTP server is up.

    Note: The public ``scan()`` function no longer calls this before every
    request (doing so wasted a full HTTP round-trip per call).  This helper
    is kept for use by benchmarks and explicit liveness probes only.
    """
    try:
        client = await _get_bridge_client()
        resp = await client.get(f"{_BRIDGE_BASE}/health", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


async def scan(subscription_id: str, provider: str = "azure") -> dict[str, Any] | None:
    """
    Run a full cloud scan via the Go engine, non-blocking.

    Tries the resident HTTP bridge first (zero fork overhead) by sending
    the request directly.  Falls back to an asyncio subprocess only if the
    bridge is not reachable (ConnectError), avoiding a wasted /health
    round-trip on every call.

    Args:
        subscription_id: Cloud subscription ID to scan
        provider: Cloud provider (default: "azure")

    Returns:
        The parsed JSON scan result, or None on failure
    """
    return await _scan_via_bridge(subscription_id, provider)


async def _scan_via_bridge(subscription_id: str, provider: str) -> dict[str, Any] | None:
    """
    POST /scan to the resident Go bridge server using the pooled HTTP client.

    Falls back to subprocess on connection errors so the caller never needs
    to pre-check bridge liveness with a separate /health call.

    Args:
        subscription_id: Cloud subscription ID to scan
        provider: Cloud provider

    Returns:
        The parsed JSON scan result, or None on failure
    """
    import httpx

    try:
        client = await _get_bridge_client()
        resp = await client.post(
            f"{_BRIDGE_BASE}/scan",
            json={"subscription_id": subscription_id, "provider": provider},
        )
        if resp.status_code == 200:
            data = resp.json()
            _log_db_stats(data.get("db_stats"))
            return data
        print(f"[go_bridge] /scan returned {resp.status_code}: {resp.text[:200]}")
        return None
    except httpx.ConnectError:
        # Bridge not running — fall back to subprocess without a separate health check
        print("[go_bridge] bridge unreachable, falling back to subprocess")
        return await _scan_via_subprocess(subscription_id)
    except Exception as exc:
        print(f"[go_bridge] bridge call failed: {exc}")
        return None


async def _scan_via_subprocess(subscription_id: str) -> dict[str, Any] | None:
    """
    Fallback: run the Go binary as a subprocess - non-blocking via
    asyncio.create_subprocess_exec (does NOT block the event loop).

    Args:
        subscription_id: Cloud subscription ID to scan

    Returns:
        The parsed JSON scan result, or None on failure
    """
    binary = _engine_binary()
    if not binary:
        print("[go_bridge] Go engine binary not found")
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            "--subscription",
            subscription_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        if proc.returncode != 0:
            print(f"[go_bridge] subprocess stderr: {stderr.decode()[:400]}")
            return None
        return json.loads(stdout.decode())
    except TimeoutError:
        print("[go_bridge] subprocess timed out")
        return None
    except Exception as exc:
        print(f"[go_bridge] subprocess error: {exc}")
        return None


async def prices(provider: str = "azure") -> dict[str, Any] | None:
    """
    Fetch price list via the Go engine bridge - non-blocking.

    Args:
        provider: Cloud provider (default: "azure")

    Returns:
        Dictionary with prices data, or None on failure
    """
    import httpx

    try:
        client = await _get_bridge_client()
        resp = await client.get(f"{_BRIDGE_BASE}/prices", params={"provider": provider})
        if resp.status_code == 200:
            return resp.json()
    except httpx.ConnectError:
        pass
    except Exception as exc:
        print(f"[go_bridge] /prices error: {exc}")
    # Fallback: subprocess
    return await _prices_via_subprocess(provider)


async def parallel_prices(
    services: list[str] | None = None,
    concurrency: int = 10,
    region: str = ""
) -> dict[str, Any] | None:
    """
    Fetch Azure pricing data using high-performance parallel scraping.
    
    This leverages the new Go parallel price scraper for 10-20x faster performance
    compared to the sequential Python implementation.

    Args:
        services: List of Azure service names to fetch (uses default list if None)
        concurrency: Number of parallel workers (default: 10)
        region: Optional region filter for regional pricing

    Returns:
        Dictionary with parallel prices data including:
        - prices: List of price items
        - count: Total number of price items
        - region: Region filter used (if any)
        - error: Error message if the request failed
        Returns None on complete failure
    """
    import httpx

    request_body = {
        "services": services or [],
        "concurrency": concurrency,
        "region": region
    }
    
    try:
        client = await _get_bridge_client()
        resp = await client.post(
            f"{_BRIDGE_BASE}/prices/parallel",
            json=request_body,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"[go_bridge] Parallel prices fetched: {data.get('count', 0)} items")
            return data
        else:
            print(f"[go_bridge] /prices/parallel returned {resp.status_code}: {resp.text[:200]}")
            return None
    except httpx.ConnectError:
        print("[go_bridge] Parallel prices requires Go bridge server to be running")
        return None
    except Exception as exc:
        print(f"[go_bridge] Parallel prices error: {exc}")
        return None


async def _prices_via_subprocess(provider: str) -> dict[str, Any] | None:
    """
    Fallback to subprocess for fetching prices.

    Args:
        provider: Cloud provider

    Returns:
        Dictionary with prices data, or None on failure
    """
    binary = _engine_binary()
    if not binary:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            "--mode",
            "prices",
            "--provider",
            provider,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode == 0:
            return json.loads(stdout.decode())
    except Exception as exc:
        print(f"[go_bridge] prices subprocess error: {exc}")
    return None


def _log_db_stats(stats: dict[str, Any] | None) -> None:
    """
    Log database statistics from Go bridge operations.

    Args:
        stats: Dictionary containing database statistics
    """
    if not stats:
        return
    print(
        f"[go_bridge][db] BatchUpsert: {stats.get('ResourceCount', '?')} resources "
        f"in {stats.get('Elapsed', '?')} "
        f"(pool_reused={stats.get('PoolReused', '?')})"
    )
