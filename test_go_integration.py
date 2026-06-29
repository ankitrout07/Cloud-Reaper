#!/usr/bin/env python3
"""
Integration Test Script for Go Components
Tests the integration between Go services and Python bridges
"""

import asyncio
import sys
import os
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import httpx


async def test_go_server_health():
    """Test health endpoints of all Go servers"""
    print("🔍 Testing Go Server Health Endpoints...")
    print("=" * 50)
    
    servers = {
        "Task Manager": "http://localhost:7071/health",
        "WebSocket Batcher": "http://localhost:7072/health", 
        "Rate Limiter": "http://localhost:7073/health",
        "Bridge": "http://localhost:7070/health"
    }
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in servers.items():
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    print(f"✅ {name}: Healthy")
                else:
                    print(f"❌ {name}: Unhealthy (status {response.status_code})")
            except Exception as e:
                print(f"❌ {name}: Connection failed ({e})")
    
    print()


async def test_task_manager_bridge():
    """Test Go Task Manager Bridge"""
    print("📋 Testing Go Task Manager Bridge...")
    print("=" * 50)
    
    try:
        from reaper.engine.core.go_task_manager import (
            GoTaskManagerBridge,
            get_task_manager_bridge,
            TaskStatus
        )
        
        bridge = get_task_manager_bridge()
        
        # Test health check
        if await bridge.health_check():
            print("✅ Task Manager health check passed")
        else:
            print("❌ Task Manager health check failed")
            return False
        
        # Test task submission
        task_id = await bridge.submit_task(
            task_type="price_scan",
            args=["test-subscription", ["eastus", "westus"]],
            metadata={"test": True}
        )
        print(f"✅ Task submitted successfully: {task_id}")
        
        # Test task status
        await asyncio.sleep(0.5)  # Give task time to start
        result = await bridge.get_task_status(task_id)
        print(f"✅ Task status retrieved: {result.status}")
        
        # Test statistics
        stats = await bridge.get_statistics()
        print(f"✅ Statistics retrieved: {stats}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import task manager bridge: {e}")
        return False
    except Exception as e:
        print(f"❌ Task manager bridge test failed: {e}")
        return False


async def test_websocket_batcher_bridge():
    """Test Go WebSocket Batcher Bridge"""
    print("📡 Testing Go WebSocket Batcher Bridge...")
    print("=" * 50)
    
    try:
        from reaper.web.go_websocket import (
            GoWebSocketBatcher,
            get_websocket_batcher
        )
        
        batcher = await get_websocket_batcher()
        
        # Test health check
        if await batcher.health_check():
            print("✅ WebSocket Batcher health check passed")
        else:
            print("❌ WebSocket Batcher health check failed")
            return False
        
        # Test message emission
        success = await batcher.emit(
            event="test_event",
            data={"message": "test message"},
            room="test_room"
        )
        if success:
            print("✅ Message emitted successfully")
        else:
            print("❌ Message emission failed")
            return False
        
        # Test statistics
        stats = await batcher.get_statistics()
        print(f"✅ Statistics retrieved: {stats}")
        
        # Test flush
        await batcher.flush_all()
        print("✅ Flush completed")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import WebSocket batcher bridge: {e}")
        return False
    except Exception as e:
        print(f"❌ WebSocket batcher bridge test failed: {e}")
        return False


async def test_rate_limiter_bridge():
    """Test Go Rate Limiter Bridge"""
    print("⚡ Testing Go Rate Limiter Bridge...")
    print("=" * 50)
    
    try:
        from reaper.web.go_ratelimiter import (
            GoRateLimiter,
            get_rate_limiter
        )
        
        limiter = await get_rate_limiter()
        
        # Test health check
        if await limiter.health_check():
            print("✅ Rate Limiter health check passed")
        else:
            print("❌ Rate Limiter health check failed")
            return False
        
        # Test rate limiting
        allowed = await limiter.allow("test_key")
        print(f"✅ Rate limit check: {'allowed' if allowed else 'denied'}")
        
        # Test statistics
        stats = await limiter.get_statistics("test_key")
        print(f"✅ Statistics retrieved: {stats}")
        
        # Test config update
        new_config = await limiter.update_config(
            key="test_key",
            requests_per_second=10.0,
            burst_size=5
        )
        print(f"✅ Config updated: {new_config}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import rate limiter bridge: {e}")
        return False
    except Exception as e:
        print(f"❌ Rate limiter bridge test failed: {e}")
        return False


async def test_base_bridge_functionality():
    """Test BaseGoBridge functionality"""
    print("🧪 Testing BaseGoBridge Functionality...")
    print("=" * 50)
    
    try:
        from reaper.web.go_bridge_base import (
            BaseGoBridge,
            GoBridgeConfig,
            GoBridgeError,
            GoBridgeConnectionError,
            GoBridgeTimeoutError
        )
        
        # Test configuration
        config = GoBridgeConfig()
        print(f"✅ Configuration loaded:")
        print(f"   - Task Manager port: {config.get_port('task_manager')}")
        print(f"   - WebSocket port: {config.get_port('websocket')}")
        print(f"   - Rate Limiter port: {config.get_port('ratelimiter')}")
        
        # Test exception hierarchy
        try:
            raise GoBridgeConnectionError("Test connection error")
        except GoBridgeError:
            print("✅ Exception hierarchy working correctly")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import base bridge: {e}")
        return False
    except Exception as e:
        print(f"❌ Base bridge test failed: {e}")
        return False


async def main():
    """Run all integration tests"""
    print("🚀 Go Components Integration Test Suite")
    print("=" * 50)
    print()
    
    # Test Go server health
    await test_go_server_health()
    
    # Test base bridge functionality
    base_ok = await test_base_bridge_functionality()
    
    # Test individual bridges
    task_ok = await test_task_manager_bridge()
    ws_ok = await test_websocket_batcher_bridge()
    rate_ok = await test_rate_limiter_bridge()
    
    # Summary
    print()
    print("📊 Test Summary")
    print("=" * 50)
    print(f"Base Bridge: {'✅ PASS' if base_ok else '❌ FAIL'}")
    print(f"Task Manager: {'✅ PASS' if task_ok else '❌ FAIL'}")
    print(f"WebSocket Batcher: {'✅ PASS' if ws_ok else '❌ FAIL'}")
    print(f"Rate Limiter: {'✅ PASS' if rate_ok else '❌ FAIL'}")
    
    all_passed = all([base_ok, task_ok, ws_ok, rate_ok])
    
    if all_passed:
        print()
        print("🎉 All integration tests passed!")
        print("Go components are ready for production use.")
        return 0
    else:
        print()
        print("⚠️  Some tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
