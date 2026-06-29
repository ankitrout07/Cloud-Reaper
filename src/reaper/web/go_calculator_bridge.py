"""
Go Calculator Bridge Client
Provides async interface to the Go cost calculator HTTP server
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


class CalculatorBridge(BaseGoBridge):
    """
    Async client for Go cost calculator engine.
    Provides high-performance batch cost calculations.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 7075,
        timeout: float = 30.0,
        enabled: bool = True
    ):
        """
        Initialize calculator bridge client.
        
        Args:
            host: Go calculator server host
            port: Go calculator server port (default 7075)
            timeout: HTTP request timeout in seconds
            enabled: Whether the bridge is enabled
        """
        super().__init__(host, port, timeout, enabled)
    
    async def calculate_monthly_cost(
        self,
        provider: str,
        resource_type: str,
        sku: str,
        quantity: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculate monthly cost for a single SKU.
        
        Args:
            provider: Cloud provider (e.g., "aws", "azure", "gcp")
            resource_type: Resource type (e.g., "compute", "storage")
            sku: SKU identifier
            quantity: Quantity of resources
            
        Returns:
            Monthly cost calculation result
        """
        return await self._make_request(
            "POST",
            "/api/calculator/monthly",
            json_data={
                "provider": provider,
                "resource_type": resource_type,
                "sku": sku,
                "quantity": quantity
            }
        )
    
    async def calculate_hourly_cost(
        self,
        provider: str,
        resource_type: str,
        sku: str,
        quantity: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculate hourly cost for a single SKU.
        
        Args:
            provider: Cloud provider (e.g., "aws", "azure", "gcp")
            resource_type: Resource type (e.g., "compute", "storage")
            sku: SKU identifier
            quantity: Quantity of resources
            
        Returns:
            Hourly cost calculation result
        """
        return await self._make_request(
            "POST",
            "/api/calculator/hourly",
            json_data={
                "provider": provider,
                "resource_type": resource_type,
                "sku": sku,
                "quantity": quantity
            }
        )
    
    async def calculate_total_hourly_burn(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate total hourly burn rate for multiple items using concurrent processing.
        
        Args:
            items: List of burn items with provider, resource_type, sku, quantity, frequency
            
        Returns:
            Total hourly burn calculation result
        """
        return await self._make_request(
            "POST",
            "/api/calculator/total_burn",
            json_data={"items": items}
        )
    
    async def batch_calculate_monthly_cost(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Perform batch monthly cost calculations using concurrent processing.
        
        Args:
            items: List of burn items with provider, resource_type, sku, quantity
            
        Returns:
            Batch monthly cost calculation results
        """
        return await self._make_request(
            "POST",
            "/api/calculator/batch_monthly",
            json_data={"items": items}
        )
    
    async def batch_calculate_hourly_cost(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Perform batch hourly cost calculations using concurrent processing.
        
        Args:
            items: List of burn items with provider, resource_type, sku, quantity
            
        Returns:
            Batch hourly cost calculation results
        """
        return await self._make_request(
            "POST",
            "/api/calculator/batch_hourly",
            json_data={"items": items}
        )
    
    async def update_price(
        self,
        provider: str,
        resource_type: str,
        sku: str,
        rate: float
    ) -> Dict[str, Any]:
        """
        Update a specific price in the price book.
        
        Args:
            provider: Cloud provider
            resource_type: Resource type
            sku: SKU identifier
            rate: New rate
            
        Returns:
            Update operation result
        """
        return await self._make_request(
            "POST",
            "/api/calculator/update_price",
            json_data={
                "provider": provider,
                "resource_type": resource_type,
                "sku": sku,
                "rate": rate
            }
        )
    
    async def load_price_book(self, price_book_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load price book data from a dictionary.
        
        Args:
            price_book_data: Price book data dictionary
            
        Returns:
            Load operation result
        """
        return await self._make_request(
            "POST",
            "/api/calculator/load_pricebook",
            json_data=price_book_data
        )
    
    async def set_currency(self, currency: str) -> Dict[str, Any]:
        """
        Set the currency for cost calculations.
        
        Args:
            currency: Currency code (e.g., "USD", "EUR", "GBP")
            
        Returns:
            Set currency operation result
        """
        return await self._make_request(
            "POST",
            "/api/calculator/set_currency",
            json_data={"currency": currency}
        )
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get calculator statistics.
        
        Returns:
            Calculator statistics including provider counts and SKU counts
        """
        return await self._make_request("GET", "/api/calculator/stats")


def create_calculator_bridge(**kwargs) -> CalculatorBridge:
    """
    Factory function to create calculator bridge with standardized configuration.
    
    Args:
        **kwargs: Additional constructor arguments
        
    Returns:
        Configured calculator bridge instance
    """
    return create_bridge_client(
        CalculatorBridge,
        "calculator",
        **kwargs
    )


# Global singleton instance
_global_calculator_bridge: Optional[CalculatorBridge] = None
_calculator_bridge_lock = asyncio.Lock()


async def get_calculator_bridge() -> CalculatorBridge:
    """
    Get or create the global calculator bridge instance.
    
    Returns:
        Global calculator bridge instance
    """
    global _global_calculator_bridge
    
    async with _calculator_bridge_lock:
        if _global_calculator_bridge is None:
            _global_calculator_bridge = create_calculator_bridge()
        return _global_calculator_bridge


async def close_calculator_bridge():
    """Close the global calculator bridge instance."""
    global _global_calculator_bridge
    
    async with _calculator_bridge_lock:
        if _global_calculator_bridge is not None:
            await _global_calculator_bridge.close()
            _global_calculator_bridge = None