#!/usr/bin/env python3
"""
Comprehensive test script for all Warehouse Operations Assistant agents.

Tests:
1. Operations Coordination Agent
2. Safety & Compliance Agent  
3. Memory Manager
4. Full integration with NVIDIA NIMs
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import test configuration directly to avoid package conflicts
import importlib.util
test_config_path = project_root / "tests" / "unit" / "test_config.py"
spec = importlib.util.spec_from_file_location("test_config", test_config_path)
test_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_config)
CHAT_ENDPOINT = test_config.CHAT_ENDPOINT
DEFAULT_TIMEOUT = test_config.DEFAULT_TIMEOUT

test_utils_path = project_root / "tests" / "unit" / "test_utils.py"
spec = importlib.util.spec_from_file_location("test_utils", test_utils_path)
test_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_utils)
cleanup_async_resource = test_utils.cleanup_async_resource

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_operations_agent():
    """Test Operations Coordination Agent."""
    logger.info("🧑‍💼 Testing Operations Coordination Agent...")
    
    try:
        from src.api.agents.operations.operations_agent import get_operations_agent
        
        # Get agent instance
        operations_agent = await get_operations_agent()
        
        # Test workforce query
        logger.info("Testing workforce management query...")
        response = await operations_agent.process_query(
            query="What's the current workforce status for the morning shift?",
            session_id="test_session_1",
            context={"user_id": "test_user_1"}
        )
        
        logger.info(f"✅ Operations Agent Response:")
        logger.info(f"   Type: {response.response_type}")
        logger.info(f"   Confidence: {response.confidence}")
        logger.info(f"   Natural Language: {response.natural_language}")
        logger.info(f"   Recommendations: {response.recommendations}")
        
        # Test task management query
        logger.info("Testing task management query...")
        response = await operations_agent.process_query(
            query="Show me all pending tasks and assign them to available staff",
            session_id="test_session_1",
            context={"user_id": "test_user_1"}
        )
        
        logger.info(f"✅ Task Management Response:")
        logger.info(f"   Type: {response.response_type}")
        logger.info(f"   Confidence: {response.confidence}")
        logger.info(f"   Natural Language: {response.natural_language}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Operations Agent test failed: {e}")
        return False

async def test_safety_agent():
    """Test Safety & Compliance Agent."""
    logger.info("🛡️ Testing Safety & Compliance Agent...")
    
    try:
        from src.api.agents.safety.safety_agent import get_safety_agent
        
        # Get agent instance
        safety_agent = await get_safety_agent()
        
        # Test incident reporting query
        logger.info("Testing incident reporting query...")
        response = await safety_agent.process_query(
            query="Report a minor slip and fall incident in Aisle A3 involving John Smith",
            session_id="test_session_2",
            context={"user_id": "test_user_2"}
        )
        
        logger.info(f"✅ Safety Agent Response:")
        logger.info(f"   Type: {response.response_type}")
        logger.info(f"   Confidence: {response.confidence}")
        logger.info(f"   Natural Language: {response.natural_language}")
        logger.info(f"   Recommendations: {response.recommendations}")
        
        # Test policy lookup query
        logger.info("Testing policy lookup query...")
        response = await safety_agent.process_query(
            query="What are the current safety policies for forklift operation?",
            session_id="test_session_2",
            context={"user_id": "test_user_2"}
        )
        
        logger.info(f"✅ Policy Lookup Response:")
        logger.info(f"   Type: {response.response_type}")
        logger.info(f"   Confidence: {response.confidence}")
        logger.info(f"   Natural Language: {response.natural_language}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Safety Agent test failed: {e}")
        return False

async def test_memory_manager():
    """Test Memory Manager."""
    logger.info("🧠 Testing Memory Manager...")
    
    try:
        from src.memory.memory_manager import get_memory_manager
        
        # Get memory manager instance
        memory_manager = await get_memory_manager()
        
        # Test user profile creation
        logger.info("Testing user profile creation...")
        user_profile = await memory_manager.create_or_update_user_profile(
            user_id="test_user_3",
            name="Test User",
            role="Warehouse Manager",
            preferences={"language": "en", "notifications": True}
        )
        
        logger.info(f"✅ User Profile Created:")
        logger.info(f"   User ID: {user_profile.user_id}")
        logger.info(f"   Name: {user_profile.name}")
        logger.info(f"   Role: {user_profile.role}")
        
        # Test session context creation
        logger.info("Testing session context creation...")
        session_context = await memory_manager.create_session_context(
            session_id=f"test_session_3_{datetime.now().timestamp()}",
            user_id="test_user_3"
        )
        
        logger.info(f"✅ Session Context Created:")
        logger.info(f"   Session ID: {session_context.session_id}")
        logger.info(f"   User ID: {session_context.user_id}")
        
        # Test conversation storage
        logger.info("Testing conversation storage...")
        turn_id = await memory_manager.store_conversation_turn(
            session_id=session_context.session_id,
            user_id="test_user_3",
            user_query="What's the inventory status for SKU123?",
            agent_response="SKU123 (Blue Pallet Jack) has 14 units in stock at Aisle A3.",
            intent="stock_lookup",
            entities={"sku": "SKU123", "location": "Aisle A3"},
            metadata={"confidence": 0.95}
        )
        
        logger.info(f"✅ Conversation Turn Stored: {turn_id}")
        
        # Test conversation history retrieval
        logger.info("Testing conversation history retrieval...")
        history = await memory_manager.get_conversation_history(session_context.session_id, limit=5)
        
        logger.info(f"✅ Conversation History Retrieved:")
        logger.info(f"   Number of turns: {len(history)}")
        if history:
            latest_turn = history[-1]
            logger.info(f"   Latest query: {latest_turn.user_query}")
            logger.info(f"   Latest response: {latest_turn.agent_response}")
        
        # Test memory stats
        logger.info("Testing memory statistics...")
        stats = await memory_manager.get_memory_stats()
        
        logger.info(f"✅ Memory Statistics:")
        logger.info(f"   Total conversations: {stats.get('total_conversations', 0)}")
        logger.info(f"   Total users: {stats.get('total_users', 0)}")
        logger.info(f"   Active sessions: {stats.get('active_sessions', 0)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Memory Manager test failed: {e}")
        return False

async def test_full_integration():
    """Test full integration with all agents and memory."""
    logger.info("🔗 Testing Full Integration...")
    
    try:
        from src.api.agents.inventory.equipment_agent import get_equipment_agent
        from src.api.agents.operations.operations_agent import get_operations_agent
        from src.api.agents.safety.safety_agent import get_safety_agent
        from src.memory.memory_manager import get_memory_manager
        
        # Get all agents and memory manager
        equipment_agent = await get_equipment_agent()
        operations_agent = await get_operations_agent()
        safety_agent = await get_safety_agent()
        memory_manager = await get_memory_manager()
        
        # Create test user and session
        user_id = "integration_test_user"
        # Use shorter session ID to fit database schema (36 char limit)
        session_id = f"int_test_{int(datetime.now().timestamp())}"
        
        await memory_manager.create_or_update_user_profile(
            user_id=user_id,
            name="Integration Test User",
            role="Warehouse Supervisor"
        )
        
        await memory_manager.create_session_context(session_id, user_id)
        
        # Test multi-agent conversation flow
        logger.info("Testing multi-agent conversation flow...")
        
        # 1. Equipment/Inventory query (equipment agent handles inventory queries)
        logger.info("1. Testing equipment/inventory query...")
        equipment_response = await equipment_agent.process_query(
            query="Check stock levels for all items in Aisle A",
            session_id=session_id,
            context={"user_id": user_id}
        )
        logger.info(f"   Equipment/Inventory Response: {equipment_response.natural_language[:100]}...")
        
        # 2. Operations query
        logger.info("2. Testing operations query...")
        operations_response = await operations_agent.process_query(
            query="Schedule the morning shift team for inventory counting",
            session_id=session_id,
            context={"user_id": user_id}
        )
        logger.info(f"   Operations Response: {operations_response.natural_language[:100]}...")
        
        # 3. Safety query
        logger.info("3. Testing safety query...")
        safety_response = await safety_agent.process_query(
            query="What safety procedures should be followed during inventory counting?",
            session_id=session_id,
            context={"user_id": user_id}
        )
        logger.info(f"   Safety Response: {safety_response.natural_language[:100]}...")
        
        # 4. Check conversation history
        logger.info("4. Checking conversation history...")
        history = await memory_manager.get_conversation_history(session_id, limit=10)
        logger.info(f"   Total conversation turns: {len(history)}")
        
        # 5. Check session context
        logger.info("5. Checking session context...")
        context = await memory_manager.get_session_context(session_id)
        if context:
            logger.info(f"   Session focus: {context.current_focus}")
            logger.info(f"   Key entities: {context.key_entities}")
        
        logger.info("✅ Full integration test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Full integration test failed: {e}")
        return False

async def test_api_endpoints():
    """Test API endpoints with all agents."""
    logger.info("🌐 Testing API Endpoints...")
    
    try:
        import aiohttp
        
        # Test chat endpoint with different intents
        test_queries = [
            "What's the stock level for SKU123?",  # Inventory
            "Show me the current workforce status",  # Operations
            "Report a safety incident in Aisle B",  # Safety
            "What are the safety policies for equipment?",  # Safety
            "Schedule tasks for the afternoon shift"  # Operations
        ]
        
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for i, query in enumerate(test_queries, 1):
                logger.info(f"Testing query {i}: {query}")
                
                payload = {
                    "message": query,
                    "session_id": f"api_test_session_{i}",
                    "context": {"user_id": f"api_test_user_{i}"}
                }
                
                async with session.post(
                    CHAT_ENDPOINT,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"   ✅ Response: {data.get('reply', '')[:100]}...")
                        logger.info(f"   Route: {data.get('route', 'unknown')}")
                        logger.info(f"   Intent: {data.get('intent', 'unknown')}")
                    else:
                        logger.error(f"   ❌ API Error: {response.status}")
                        return False
        
        logger.info("✅ API endpoint tests completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ API endpoint test failed: {e}")
        return False

async def main():
    """Run all tests."""
    logger.info("🚀 Starting Comprehensive Agent Tests...")
    logger.info("=" * 60)
    
    test_results = {}
    
    # Test individual agents
    test_results["operations_agent"] = await test_operations_agent()
    logger.info("-" * 60)
    
    test_results["safety_agent"] = await test_safety_agent()
    logger.info("-" * 60)
    
    test_results["memory_manager"] = await test_memory_manager()
    logger.info("-" * 60)
    
    # Test full integration
    test_results["full_integration"] = await test_full_integration()
    logger.info("-" * 60)
    
    # Test API endpoints
    test_results["api_endpoints"] = await test_api_endpoints()
    logger.info("-" * 60)
    
    # Summary
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! The Warehouse Operations Assistant is fully functional!")
    else:
        logger.warning(f"⚠️ {total - passed} tests failed. Please check the logs above.")
    
    return passed == total

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        sys.exit(1)
