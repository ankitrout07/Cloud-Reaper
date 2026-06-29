# src/reaper/web/go_bridge.py
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
    """
    Quick health check - returns True if the bridge HTTP server is up.

    Returns:
        True if the bridge server is responding, False otherwise
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{_BRIDGE_BASE}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def scan(subscription_id: str, provider: str = "azure") -> dict[str, Any] | None:
    """
    Run a full cloud scan via the Go engine, non-blocking.

    Tries the resident HTTP bridge first (zero fork overhead).
    Falls back to asyncio subprocess if the bridge is not running.

    Args:
        subscription_id: Cloud subscription ID to scan
        provider: Cloud provider (default: "azure")

    Returns:
        The parsed JSON scan result, or None on failure
    """
    if await _is_bridge_alive():
        return await _scan_via_bridge(subscription_id, provider)
    return await _scan_via_subprocess(subscription_id)


async def _scan_via_bridge(subscription_id: str, provider: str) -> dict[str, Any] | None:
    """
    POST /scan to the resident Go bridge server - non-blocking.

    Args:
        subscription_id: Cloud subscription ID to scan
        provider: Cloud provider

    Returns:
        The parsed JSON scan result, or None on failure
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
    if await _is_bridge_alive():
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{_BRIDGE_BASE}/prices", params={"provider": provider})
                if resp.status_code == 200:
                    return resp.json()
        except Exception as exc:
            print(f"[go_bridge] /prices error: {exc}")
    # Fallback: subprocess
    return await _prices_via_subprocess(provider)


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
