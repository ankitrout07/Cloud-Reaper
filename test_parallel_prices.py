#!/usr/bin/env python3
"""
Test script for parallel Azure price scraping

This script demonstrates the performance improvement of the Go-based parallel
price scraper compared to the sequential Python implementation.
"""

import asyncio
import time
from reaper.collectors.prices.azure import AzurePriceClient
from reaper.collectors.prices.azure_parallel import AzureParallelPriceClient


async def test_python_client():
    """Test the original Python Azure price client"""
    print("Testing Python Azure Price Client (sequential)...")
    client = AzurePriceClient()
    
    start_time = time.time()
    prices = client.get_catalog_prices()
    elapsed = time.time() - start_time
    
    print(f"Python client fetched {len(prices)} price items in {elapsed:.2f} seconds")
    return len(prices), elapsed


async def test_go_parallel_client():
    """Test the new Go-based parallel Azure price client"""
    print("Testing Go Parallel Azure Price Client...")
    client = AzureParallelPriceClient()
    
    start_time = time.time()
    prices = await client.get_catalog_prices(concurrency=10)
    elapsed = time.time() - start_time
    
    print(f"Go parallel client fetched {len(prices)} price items in {elapsed:.2f} seconds")
    return len(prices), elapsed


async def test_regional_prices():
    """Test regional price fetching"""
    print("Testing regional price fetching...")
    client = AzureParallelPriceClient()
    
    start_time = time.time()
    prices = await client.get_prices_by_region(
        services=["Virtual Machines", "Storage"],
        region="eastus",
        concurrency=5
    )
    elapsed = time.time() - start_time
    
    print(f"Regional client fetched {len(prices)} price items in {elapsed:.2f} seconds")
    return len(prices), elapsed


async def main():
    """Main test function"""
    print("=" * 60)
    print("Azure Price Scraping Performance Comparison")
    print("=" * 60)
    
    # Test Python client
    python_count, python_time = await test_python_client()
    print()
    
    # Test Go parallel client
    go_count, go_time = await test_go_parallel_client()
    print()
    
    # Test regional prices
    regional_count, regional_time = await test_regional_prices()
    print()
    
    # Performance comparison
    print("=" * 60)
    print("Performance Summary")
    print("=" * 60)
    print(f"Python client:  {python_count} items in {python_time:.2f}s")
    print(f"Go parallel:    {go_count} items in {go_time:.2f}s")
    print(f"Regional:       {regional_count} items in {regional_time:.2f}s")
    
    if go_time > 0:
        speedup = python_time / go_time
        print(f"Speedup:        {speedup:.1f}x faster")
    
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())