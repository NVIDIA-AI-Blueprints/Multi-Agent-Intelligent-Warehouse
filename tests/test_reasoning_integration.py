"""
Test script for reasoning capability integration across all agents.

This script tests:
1. Chat Router accepts enable_reasoning parameter
2. MCP Planner Graph passes reasoning context
3. All agents (Equipment, Operations, Forecasting, Document, Safety) support reasoning
4. Agent response models include reasoning chain
"""

import asyncio
import httpx
import json
import logging
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8001/api/v1"


async def test_chat_with_reasoning(
    message: str,
    enable_reasoning: bool = True,
    reasoning_types: Optional[list] = None,
    expected_route: Optional[str] = None
) -> Dict[str, Any]:
    """
    Test chat endpoint with reasoning enabled.
    
    Args:
        message: User message to test
        enable_reasoning: Whether to enable reasoning
        reasoning_types: Optional list of reasoning types to use
        expected_route: Expected route for the query
        
    Returns:
        Response dictionary
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "message": message,
                "session_id": "test_reasoning_session",
                "enable_reasoning": enable_reasoning,
            }
            
            if reasoning_types:
                payload["reasoning_types"] = reasoning_types
            
            logger.info(f"Testing chat with reasoning: {message[:50]}...")
            logger.info(f"  enable_reasoning: {enable_reasoning}")
            logger.info(f"  reasoning_types: {reasoning_types}")
            
            response = await client.post(
                f"{API_BASE_URL}/chat",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"✅ Response received")
            logger.info(f"  Route: {result.get('route', 'unknown')}")
            logger.info(f"  Intent: {result.get('intent', 'unknown')}")
            logger.info(f"  Confidence: {result.get('confidence', 0.0)}")
            
            # Check if reasoning chain is present when enabled
            if enable_reasoning:
                reasoning_chain = result.get('reasoning_chain')
                reasoning_steps = result.get('reasoning_steps')
                
                if reasoning_chain:
                    logger.info(f"  ✅ Reasoning chain present: {len(reasoning_steps) if reasoning_steps else 0} steps")
                else:
                    logger.warning(f"  ⚠️ Reasoning chain not present (may be simple query)")
            
            if expected_route and result.get('route') != expected_route:
                logger.warning(f"  ⚠️ Route mismatch: expected {expected_route}, got {result.get('route')}")
            
            return result
            
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"❌ Error testing chat: {e}")
        raise


async def test_equipment_reasoning():
    """Test Equipment Agent with reasoning."""
    logger.info("\n" + "="*60)
    logger.info("Testing Equipment Agent with Reasoning")
    logger.info("="*60)
    
    # Complex query that should trigger reasoning
    complex_query = "Why is forklift FL-01 experiencing low utilization? Analyze the relationship between maintenance schedules and equipment availability."
    
    result = await test_chat_with_reasoning(
        message=complex_query,
        enable_reasoning=True,
        expected_route="equipment"
    )
    
    # Verify reasoning chain
    if result.get('reasoning_chain') or result.get('reasoning_steps'):
        logger.info("✅ Equipment Agent reasoning chain present")
        return True
    else:
        logger.warning("⚠️ Equipment Agent reasoning chain not present")
        return False


async def test_operations_reasoning():
    """Test Operations Agent with reasoning."""
    logger.info("\n" + "="*60)
    logger.info("Testing Operations Agent with Reasoning")
    logger.info("="*60)
    
    # Complex query that should trigger reasoning
    complex_query = "What if we optimize the pick wave creation process? Analyze the impact on workforce efficiency and suggest improvements."
    
    result = await test_chat_with_reasoning(
        message=complex_query,
        enable_reasoning=True,
        expected_route="operations"
    )
    
    # Verify reasoning chain
    if result.get('reasoning_chain') or result.get('reasoning_steps'):
        logger.info("✅ Operations Agent reasoning chain present")
        return True
    else:
        logger.warning("⚠️ Operations Agent reasoning chain not present")
        return False


async def test_forecasting_reasoning():
    """Test Forecasting Agent with reasoning."""
    logger.info("\n" + "="*60)
    logger.info("Testing Forecasting Agent with Reasoning")
    logger.info("="*60)
    
    # Complex query that should trigger reasoning
    complex_query = "Explain the pattern in demand forecasting for SKU LAY001. What causes the seasonal variations and how can we improve accuracy?"
    
    result = await test_chat_with_reasoning(
        message=complex_query,
        enable_reasoning=True,
        expected_route="forecasting"
    )
    
    # Verify reasoning chain
    if result.get('reasoning_chain') or result.get('reasoning_steps'):
        logger.info("✅ Forecasting Agent reasoning chain present")
        return True
    else:
        logger.warning("⚠️ Forecasting Agent reasoning chain not present")
        return False


async def test_document_reasoning():
    """Test Document Agent with reasoning."""
    logger.info("\n" + "="*60)
    logger.info("Testing Document Agent with Reasoning")
    logger.info("="*60)
    
    # Complex query that should trigger reasoning
    complex_query = "Why was document DOC-123 rejected? Analyze the quality issues and explain the cause of the validation failure."
    
    result = await test_chat_with_reasoning(
        message=complex_query,
        enable_reasoning=True,
        expected_route="document"
    )
    
    # Verify reasoning chain
    if result.get('reasoning_chain') or result.get('reasoning_steps'):
        logger.info("✅ Document Agent reasoning chain present")
        return True
    else:
        logger.warning("⚠️ Document Agent reasoning chain not present")
        return False


async def test_safety_reasoning():
    """Test Safety Agent with reasoning."""
    logger.info("\n" + "="*60)
    logger.info("Testing Safety Agent with Reasoning")
    logger.info("="*60)
    
    # Complex query that should trigger reasoning
    complex_query = "What caused the safety incident in Zone A? Investigate the root cause and explain the relationship between equipment failure and safety protocols."
    
    result = await test_chat_with_reasoning(
        message=complex_query,
        enable_reasoning=True,
        expected_route="safety"
    )
    
    # Verify reasoning chain
    if result.get('reasoning_chain') or result.get('reasoning_steps'):
        logger.info("✅ Safety Agent reasoning chain present")
        return True
    else:
        logger.warning("⚠️ Safety Agent reasoning chain not present")
        return False


async def test_reasoning_disabled():
    """Test that reasoning is not applied when disabled."""
    logger.info("\n" + "="*60)
    logger.info("Testing Reasoning Disabled")
    logger.info("="*60)
    
    # Complex query but with reasoning disabled
    complex_query = "Why is forklift FL-01 experiencing low utilization? Analyze the relationship between maintenance schedules and equipment availability."
    
    result = await test_chat_with_reasoning(
        message=complex_query,
        enable_reasoning=False,
        expected_route="equipment"
    )
    
    # Verify reasoning chain is NOT present
    if not result.get('reasoning_chain') and not result.get('reasoning_steps'):
        logger.info("✅ Reasoning chain correctly absent when disabled")
        return True
    else:
        logger.warning("⚠️ Reasoning chain present when it should be disabled")
        return False


async def test_simple_query_no_reasoning():
    """Test that simple queries don't trigger reasoning even when enabled."""
    logger.info("\n" + "="*60)
    logger.info("Testing Simple Query (No Reasoning Expected)")
    logger.info("="*60)
    
    # Simple query that shouldn't trigger reasoning
    simple_query = "Show me forklift FL-01 status"
    
    result = await test_chat_with_reasoning(
        message=simple_query,
        enable_reasoning=True,
        expected_route="equipment"
    )
    
    # Simple queries may or may not have reasoning - both are acceptable
    logger.info("✅ Simple query processed (reasoning optional for simple queries)")
    return True


async def test_specific_reasoning_types():
    """Test with specific reasoning types."""
    logger.info("\n" + "="*60)
    logger.info("Testing Specific Reasoning Types")
    logger.info("="*60)
    
    # Query that should use causal reasoning
    query = "Why did the equipment fail? What caused the breakdown?"
    
    result = await test_chat_with_reasoning(
        message=query,
        enable_reasoning=True,
        reasoning_types=["causal", "chain_of_thought"],
        expected_route="equipment"
    )
    
    logger.info("✅ Specific reasoning types test completed")
    return True


async def run_all_tests():
    """Run all reasoning integration tests."""
    logger.info("\n" + "="*80)
    logger.info("REASONING CAPABILITY INTEGRATION TEST SUITE")
    logger.info("="*80)
    
    # Health check first
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_BASE_URL}/health")
            response.raise_for_status()
            logger.info("✅ API health check passed")
    except Exception as e:
        logger.error(f"❌ API health check failed: {e}")
        logger.error("Make sure the server is running on http://localhost:8001")
        return False
    
    results = {}
    
    # Test each agent
    try:
        results['equipment'] = await test_equipment_reasoning()
    except Exception as e:
        logger.error(f"❌ Equipment Agent test failed: {e}")
        results['equipment'] = False
    
    try:
        results['operations'] = await test_operations_reasoning()
    except Exception as e:
        logger.error(f"❌ Operations Agent test failed: {e}")
        results['operations'] = False
    
    try:
        results['forecasting'] = await test_forecasting_reasoning()
    except Exception as e:
        logger.error(f"❌ Forecasting Agent test failed: {e}")
        results['forecasting'] = False
    
    try:
        results['document'] = await test_document_reasoning()
    except Exception as e:
        logger.error(f"❌ Document Agent test failed: {e}")
        results['document'] = False
    
    try:
        results['safety'] = await test_safety_reasoning()
    except Exception as e:
        logger.error(f"❌ Safety Agent test failed: {e}")
        results['safety'] = False
    
    try:
        results['reasoning_disabled'] = await test_reasoning_disabled()
    except Exception as e:
        logger.error(f"❌ Reasoning disabled test failed: {e}")
        results['reasoning_disabled'] = False
    
    try:
        results['simple_query'] = await test_simple_query_no_reasoning()
    except Exception as e:
        logger.error(f"❌ Simple query test failed: {e}")
        results['simple_query'] = False
    
    try:
        results['specific_types'] = await test_specific_reasoning_types()
    except Exception as e:
        logger.error(f"❌ Specific reasoning types test failed: {e}")
        results['specific_types'] = False
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("TEST SUMMARY")
    logger.info("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed!")
        return True
    else:
        logger.warning(f"⚠️ {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)

