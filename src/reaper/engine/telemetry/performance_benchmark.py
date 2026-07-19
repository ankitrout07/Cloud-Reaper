import asyncio
import json
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class BenchmarkResult:
    """Simple benchmark result container."""

    name: str
    elapsed_seconds: float
    items_processed: int
    throughput_per_second: float
    memory_estimate_mb: float


class PerformanceBenchmarkRunner:
    """Measure and compare Python and Go-backed execution paths."""

    def __init__(self, iterations: int = 3) -> None:
        self.iterations = max(1, iterations)

    def run(self, name: str, fn: Callable[[], Any]) -> BenchmarkResult:
        """Run a benchmark function and collect basic latency and throughput metrics."""
        samples: list[float] = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            result = fn()
            elapsed = time.perf_counter() - start
            samples.append(elapsed)
            if isinstance(result, (int, float)):
                continue

        if not samples:
            raise RuntimeError("Benchmark did not collect any samples")

        avg_elapsed = statistics.mean(samples)
        items_processed = self._estimate_items(result)
        throughput = items_processed / avg_elapsed if avg_elapsed > 0 else 0.0
        memory_estimate_mb = self._estimate_memory_mb(items_processed, avg_elapsed)
        return BenchmarkResult(
            name=name,
            elapsed_seconds=avg_elapsed,
            items_processed=items_processed,
            throughput_per_second=throughput,
            memory_estimate_mb=memory_estimate_mb,
        )

    def _estimate_items(self, result: Any) -> int:
        if isinstance(result, list):
            return len(result)
        if isinstance(result, dict):
            return len(result)
        if isinstance(result, tuple):
            return len(result)
        return 1

    def _estimate_memory_mb(self, items_processed: int, elapsed_seconds: float) -> float:
        base_mb = 8.0 + min(items_processed / 1000.0, 50.0)
        if elapsed_seconds > 0:
            return round(base_mb + (items_processed / 50000.0), 3)
        return round(base_mb, 3)

    def compare(self, python_fn: Callable[[], Any], go_fn: Callable[[], Any], name: str) -> dict[str, Any]:
        """Compare Python and Go-backed implementations for a target workload."""
        python_result = self.run(f"{name} (python)", python_fn)
        go_result = self.run(f"{name} (go)", go_fn)
        return {
            "benchmark": name,
            "python": {
                "elapsed_seconds": round(python_result.elapsed_seconds, 4),
                "throughput_per_second": round(python_result.throughput_per_second, 2),
                "memory_estimate_mb": round(python_result.memory_estimate_mb, 3),
            },
            "go": {
                "elapsed_seconds": round(go_result.elapsed_seconds, 4),
                "throughput_per_second": round(go_result.throughput_per_second, 2),
                "memory_estimate_mb": round(go_result.memory_estimate_mb, 3),
            },
            "improvement": {
                "latency_improvement": self._format_percent_change(
                    python_result.elapsed_seconds, go_result.elapsed_seconds
                ),
                "throughput_improvement": self._format_percent_change(
                    python_result.throughput_per_second, go_result.throughput_per_second
                ),
                "memory_improvement": self._format_percent_change(
                    python_result.memory_estimate_mb, go_result.memory_estimate_mb
                ),
            },
        }

    def _format_percent_change(self, before: float, after: float) -> str:
        if before <= 0:
            return "n/a"
        delta = ((before - after) / before) * 100.0
        return f"{delta:+.1f}%"


async def benchmark_go_bridge() -> dict[str, Any]:
    """Probe the Go bridge health and return a summary suitable for CLI reporting."""
    try:
        from reaper.integrations.go_bridge import _is_bridge_alive

        alive = await _is_bridge_alive()
        return {
            "bridge_available": alive,
            "bridge_port": int(os.getenv("REAPER_GO_BRIDGE_PORT", "7070")),
            "status": "healthy" if alive else "unavailable",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"bridge_available": False, "status": "error", "error": str(exc)}


def print_benchmark_report(report: dict[str, Any]) -> None:
    """Print a human-readable benchmark report."""
    print("\n=== CLOUD-REAPER GO MIGRATION BENCHMARK ===")
    print(f"Benchmark: {report.get('benchmark', 'unknown')}")
    print(f"Python elapsed: {report['python']['elapsed_seconds']:.4f}s")
    print(f"Go elapsed: {report['go']['elapsed_seconds']:.4f}s")
    print(f"Latency improvement: {report['improvement']['latency_improvement']}")
    print(f"Throughput improvement: {report['improvement']['throughput_improvement']}")
    print(f"Memory improvement: {report['improvement']['memory_improvement']}")
    if report.get("bridge"):
        print(f"Bridge status: {report['bridge']['status']}")
