"""
Go Anomaly Detection Bridge Client
Provides async interface to the Go anomaly detection HTTP server
"""

import asyncio
from typing import Any, Dict, List, Optional

from reaper.web.go_bridge_base import (
    BaseGoBridge,
    GoBridgeConfig,
    GoBridgeConnectionError,
    GoBridgeTimeoutError,
    create_bridge_client
)


class AnomalyBridge(BaseGoBridge):
    """
    Async client for Go anomaly detection engine.
    Provides real-time anomaly detection with statistical methods.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 7076,
        timeout: float = 30.0,
        enabled: bool = True
    ):
        """
        Initialize anomaly detection bridge client.
        
        Args:
            host: Go anomaly detection server host
            port: Go anomaly detection server port (default 7076)
            timeout: HTTP request timeout in seconds
            enabled: Whether the bridge is enabled
        """
        super().__init__(host, port, timeout, enabled)
    
    async def detect_anomaly(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[int] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Detect anomaly for a single metric.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            timestamp: Unix timestamp (optional, defaults to current time)
            labels: Metric labels (optional)
            
        Returns:
            Anomaly detection result
        """
        return await self._make_request(
            "POST",
            "/api/anomaly/detect",
            json_data={
                "metric_name": metric_name,
                "value": value,
                "timestamp": timestamp or 0,
                "labels": labels or {}
            }
        )
    
    async def batch_detect_anomalies(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect anomalies for multiple metrics in batch.
        
        Args:
            metrics: List of metric dictionaries with metric_name, value, timestamp, labels
            
        Returns:
            Batch anomaly detection results
        """
        return await self._make_request(
            "POST",
            "/api/anomaly/batch_detect",
            json_data={"metrics": metrics}
        )
    
    async def get_metric_buffer(self, metric_name: str) -> Dict[str, Any]:
        """
        Get the current metric buffer for a specific metric.
        
        Args:
            metric_name: Name of the metric
            
        Returns:
            Metric buffer data
        """
        return await self._make_request(
            "GET",
            "/api/anomaly/buffer",
            params={"metric_name": metric_name}
        )
    
    async def clear_buffer(self, metric_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear metric buffer for a specific metric or all metrics.
        
        Args:
            metric_name: Name of the metric to clear (optional, clears all if not provided)
            
        Returns:
            Clear operation result
        """
        return await self._make_request(
            "POST",
            "/api/anomaly/clear_buffer",
            json_data={"metric_name": metric_name or ""}
        )
    
    async def set_config(
        self,
        threshold: Optional[float] = None,
        window_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Set anomaly detection configuration.
        
        Args:
            threshold: Anomaly detection threshold (optional)
            window_size: Window size for statistical calculations (optional)
            
        Returns:
            Configuration update result
        """
        config_data = {}
        if threshold is not None:
            config_data["threshold"] = threshold
        if window_size is not None:
            config_data["window_size"] = window_size
        
        return await self._make_request(
            "POST",
            "/api/anomaly/config",
            json_data=config_data
        )
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get anomaly detection statistics.
        
        Returns:
            Statistics including counts, mean, std_dev, etc.
        """
        return await self._make_request("GET", "/api/anomaly/stats")


def create_anomaly_bridge(**kwargs) -> AnomalyBridge:
    """
    Factory function to create anomaly detection bridge with standardized configuration.
    
    Args:
        **kwargs: Additional constructor arguments
        
    Returns:
        Configured anomaly detection bridge instance
    """
    return create_bridge_client(
        AnomalyBridge,
        "anomaly",
        **kwargs
    )


# Global singleton instance
_global_anomaly_bridge: Optional[AnomalyBridge] = None
_anomaly_bridge_lock = asyncio.Lock()


async def get_anomaly_bridge() -> AnomalyBridge:
    """
    Get or create the global anomaly detection bridge instance.
    
    Returns:
        Global anomaly detection bridge instance
    """
    global _global_anomaly_bridge
    
    async with _anomaly_bridge_lock:
        if _global_anomaly_bridge is None:
            _global_anomaly_bridge = create_anomaly_bridge()
        return _global_anomaly_bridge


async def close_anomaly_bridge():
    """Close the global anomaly detection bridge instance."""
    global _global_anomaly_bridge
    
    async with _anomaly_bridge_lock:
        if _global_anomaly_bridge is not None:
            await _global_anomaly_bridge.close()
            _global_anomaly_bridge = None