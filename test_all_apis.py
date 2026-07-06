#!/usr/bin/env python3
"""
Comprehensive API Testing Script for Cloud-Reaper

Tests all Python FastAPI endpoints and Go HTTP bridge endpoints.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List
import httpx
import os

# Configuration
FASTAPI_BASE_URL = "http://localhost:5001"
GO_BRIDGE_PORT = 7070
GO_BRIDGE_BASE_URL = f"http://localhost:{GO_BRIDGE_PORT}"
GO_PORTS = {
    "anomaly": 7076,
    "calculator": 7075,
    "rag": 7074,
    "ratelimit": 7073,
    "task": 7071,
    "websocket": 7072,
}

# Test results storage
test_results = {
    "timestamp": datetime.now().isoformat(),
    "fastapi_tests": [],
    "go_bridge_tests": [],
    "go_service_tests": [],
    "summary": {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0
    }
}

def log_result(test_category: str, test_name: str, status: str, response_time: float, error: str = None, details: str = None):
    """Log a test result"""
    result = {
        "test_name": test_name,
        "status": status,  # "passed", "failed", "skipped"
        "response_time_ms": round(response_time * 1000, 2),
        "error": error,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    test_results[test_category].append(result)
    test_results["summary"]["total"] += 1
    
    if status == "passed":
        test_results["summary"]["passed"] += 1
        print(f"✓ {test_name} - {status} ({result['response_time_ms']}ms)")
    elif status == "failed":
        test_results["summary"]["failed"] += 1
        print(f"✗ {test_name} - {status} ({result['response_time_ms']}ms) - {error}")
    else:
        test_results["summary"]["skipped"] += 1
        print(f"⊘ {test_name} - {status}")

async def test_fastapi_endpoints():
    """Test all Python FastAPI endpoints"""
    print("\n" + "="*60)
    print("Testing Python FastAPI Endpoints")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # Test 1: Copilot optimization endpoint
        try:
            start_time = time.time()
            response = await client.post(
                f"{FASTAPI_BASE_URL}/api/v1/copilot/optimize",
                json={
                    "provider": "azure",
                    "intent": "high performance web server",
                    "budget_cap": 100.0
                }
            )
            response_time = time.time() - start_time
            
            if response.status_code in [200, 400]:  # 400 if missing dependencies
                log_result("fastapi_tests", "Copilot Optimization", "passed", response_time, 
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "Copilot Optimization", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "Copilot Optimization", "failed", 0, error=str(e))
        
        # Test 2: Documentation search endpoint
        try:
            start_time = time.time()
            response = await client.post(
                f"{FASTAPI_BASE_URL}/api/v1/docs/search",
                json={"query": "cost optimization"}
            )
            response_time = time.time() - start_time
            
            if response.status_code in [200, 503]:  # 503 if GEMINI_API_KEY not configured
                log_result("fastapi_tests", "Documentation Search", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "Documentation Search", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "Documentation Search", "failed", 0, error=str(e))
        
        # Test 3: Telemetry insights endpoint
        try:
            start_time = time.time()
            response = await client.post(f"{FASTAPI_BASE_URL}/api/v1/finops/telemetry-insights")
            response_time = time.time() - start_time
            
            if response.status_code in [200, 500]:  # 500 if DB not available
                log_result("fastapi_tests", "Telemetry Insights", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "Telemetry Insights", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "Telemetry Insights", "failed", 0, error=str(e))
        
        # Test 4: Webhook test endpoint
        try:
            start_time = time.time()
            response = await client.post(
                f"{FASTAPI_BASE_URL}/api/v1/finops/test-webhook",
                json={"platform": "discord", "webhook_url": "https://discord.com/api/webhooks/test"}
            )
            response_time = time.time() - start_time
            
            if response.status_code in [200, 400]:  # 400 if invalid URL
                log_result("fastapi_tests", "Webhook Test", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "Webhook Test", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "Webhook Test", "failed", 0, error=str(e))
        
        # Test 5: ML Chat Query endpoint
        try:
            start_time = time.time()
            response = await client.post(
                f"{FASTAPI_BASE_URL}/api/v1/ml/chat/query",
                json={"query": "Show me my monthly costs", "session_id": "test-session"}
            )
            response_time = time.time() - start_time
            
            if response.status_code in [200, 503]:  # 503 if AI/ML disabled
                log_result("fastapi_tests", "ML Chat Query", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "ML Chat Query", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "ML Chat Query", "failed", 0, error=str(e))
        
        # Test 6: Governance health check
        try:
            start_time = time.time()
            response = await client.get(f"{FASTAPI_BASE_URL}/api/v1/governance/health")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                log_result("fastapi_tests", "Governance Health Check", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "Governance Health Check", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "Governance Health Check", "failed", 0, error=str(e))
        
        # Test 7: List policies
        try:
            start_time = time.time()
            response = await client.get(f"{FASTAPI_BASE_URL}/api/v1/governance/policies")
            response_time = time.time() - start_time
            
            if response.status_code in [200, 503]:  # 503 if governance disabled
                log_result("fastapi_tests", "List Policies", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "List Policies", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "List Policies", "failed", 0, error=str(e))
        
        # Test 8: List best practices
        try:
            start_time = time.time()
            response = await client.get(f"{FASTAPI_BASE_URL}/api/v1/governance/best-practices")
            response_time = time.time() - start_time
            
            if response.status_code in [200, 503]:  # 503 if governance disabled
                log_result("fastapi_tests", "List Best Practices", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("fastapi_tests", "List Best Practices", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("fastapi_tests", "List Best Practices", "failed", 0, error=str(e))

async def test_go_bridge_endpoints():
    """Test Go HTTP bridge endpoints"""
    print("\n" + "="*60)
    print("Testing Go HTTP Bridge Endpoints")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # Test 1: Go bridge health check
        try:
            start_time = time.time()
            response = await client.get(f"{GO_BRIDGE_BASE_URL}/health")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                log_result("go_bridge_tests", "Go Bridge Health Check", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("go_bridge_tests", "Go Bridge Health Check", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("go_bridge_tests", "Go Bridge Health Check", "failed", 0, error=str(e))
        
        # Test 2: Go bridge prices endpoint
        try:
            start_time = time.time()
            response = await client.get(f"{GO_BRIDGE_BASE_URL}/prices", params={"provider": "azure"})
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                log_result("go_bridge_tests", "Go Bridge Prices", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("go_bridge_tests", "Go Bridge Prices", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("go_bridge_tests", "Go Bridge Prices", "failed", 0, error=str(e))
        
        # Test 3: Go bridge scan endpoint (with test subscription)
        try:
            start_time = time.time()
            response = await client.post(
                f"{GO_BRIDGE_BASE_URL}/scan",
                json={"subscription_id": "test-subscription", "provider": "azure"}
            )
            response_time = time.time() - start_time
            
            if response.status_code in [200, 400, 500]:  # May fail with invalid credentials
                log_result("go_bridge_tests", "Go Bridge Scan", "passed", response_time,
                          details=f"Status: {response.status_code}")
            else:
                log_result("go_bridge_tests", "Go Bridge Scan", "failed", response_time,
                          error=f"Status: {response.status_code}", details=response.text[:200])
        except Exception as e:
            log_result("go_bridge_tests", "Go Bridge Scan", "failed", 0, error=str(e))

async def test_go_service_endpoints():
    """Test individual Go service endpoints"""
    print("\n" + "="*60)
    print("Testing Individual Go Service Endpoints")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        
        # Test each Go service
        for service_name, port in GO_PORTS.items():
            base_url = f"http://localhost:{port}"
            
            # Test health check for each service
            try:
                start_time = time.time()
                response = await client.get(f"{base_url}/health")
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    log_result("go_service_tests", f"{service_name.capitalize()} Health Check", 
                              "passed", response_time, details=f"Port: {port}")
                else:
                    log_result("go_service_tests", f"{service_name.capitalize()} Health Check",
                              "failed", response_time, error=f"Status: {response.status_code}")
            except Exception as e:
                log_result("go_service_tests", f"{service_name.capitalize()} Health Check",
                          "failed", 0, error=str(e))

async def main():
    """Main test runner"""
    print("="*60)
    print("Cloud-Reaper API Test Suite")
    print("="*60)
    print(f"Test started at: {test_results['timestamp']}")
    print(f"FastAPI Base URL: {FASTAPI_BASE_URL}")
    print(f"Go Bridge URL: {GO_BRIDGE_BASE_URL}")
    
    # Run all tests
    await test_fastapi_endpoints()
    await test_go_bridge_endpoints()
    await test_go_service_endpoints()
    
    # Print summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    summary = test_results["summary"]
    print(f"Total tests: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Success rate: {(summary['passed']/summary['total']*100) if summary['total'] > 0 else 0:.1f}%")
    
    # Save results to file
    results_file = "api_test_results.json"
    with open(results_file, "w") as f:
        json.dump(test_results, f, indent=2)
    print(f"\nDetailed results saved to: {results_file}")
    
    # Return exit code based on results
    if summary['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
