#!/usr/bin/env python3
"""
Test Chat Functionality

Tests the warehouse operational assistant chat functionality
with simple queries to identify and fix issues.
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatTester:
    """Test chat functionality."""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_health(self) -> bool:
        """Test API health."""
        try:
            async with self.session.get(f"{self.base_url}/api/v1/health/simple") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Health check passed: {data}")
                    return True
                else:
                    logger.error(f"❌ Health check failed: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ Health check error: {e}")
            return False
    
    async def test_chat(self, message: str) -> Dict[str, Any]:
        """Test chat functionality."""
        try:
            payload = {
                "message": message,
                "session_id": "test_session",
                "context": {}
            }
            
            logger.info(f"🔍 Testing chat with message: '{message}'")
            
            async with self.session.post(
                f"{self.base_url}/api/v1/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Chat response received:")
                    logger.info(f"   Reply: {data.get('reply', 'No reply')}")
                    logger.info(f"   Route: {data.get('route', 'Unknown')}")
                    logger.info(f"   Intent: {data.get('intent', 'Unknown')}")
                    logger.info(f"   Confidence: {data.get('confidence', 'Unknown')}")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Chat failed with status {response.status}: {error_text}")
                    return {"error": f"HTTP {response.status}", "details": error_text}
                    
        except Exception as e:
            logger.error(f"❌ Chat error: {e}")
            return {"error": str(e)}
    
    async def run_tests(self):
        """Run comprehensive chat tests."""
        logger.info("🚀 Starting Chat Functionality Tests")
        logger.info("=" * 50)
        
        # Test 1: Health Check
        logger.info("\n1️⃣ Testing API Health...")
        health_ok = await self.test_health()
        if not health_ok:
            logger.error("❌ API health check failed. Stopping tests.")
            return
        
        # Test 2: Simple Equipment Query
        logger.info("\n2️⃣ Testing Simple Equipment Query...")
        equipment_response = await self.test_chat("What equipment do we have?")
        
        # Test 3: Safety Query
        logger.info("\n3️⃣ Testing Safety Query...")
        safety_response = await self.test_chat("What are the safety procedures?")
        
        # Test 4: Operations Query
        logger.info("\n4️⃣ Testing Operations Query...")
        operations_response = await self.test_chat("What tasks are pending?")
        
        # Test 5: General Query
        logger.info("\n5️⃣ Testing General Query...")
        general_response = await self.test_chat("Hello, how are you?")
        
        # Test 6: Complex Query
        logger.info("\n6️⃣ Testing Complex Query...")
        complex_response = await self.test_chat("I need to find a forklift for loading dock operations. What's available?")
        
        # Summary
        logger.info("\n📊 Test Summary:")
        logger.info("=" * 50)
        
        tests = [
            ("Equipment Query", equipment_response),
            ("Safety Query", safety_response),
            ("Operations Query", operations_response),
            ("General Query", general_response),
            ("Complex Query", complex_response)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, response in tests:
            if "error" not in response and response.get("reply"):
                logger.info(f"✅ {test_name}: PASSED")
                passed += 1
            else:
                logger.info(f"❌ {test_name}: FAILED")
                if "error" in response:
                    logger.info(f"   Error: {response['error']}")
        
        logger.info(f"\n🎯 Results: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests passed! Chat functionality is working correctly.")
        else:
            logger.warning("⚠️ Some tests failed. Check the logs above for details.")

async def main():
    """Main test execution."""
    async with ChatTester() as tester:
        await tester.run_tests()

if __name__ == "__main__":
    asyncio.run(main())
