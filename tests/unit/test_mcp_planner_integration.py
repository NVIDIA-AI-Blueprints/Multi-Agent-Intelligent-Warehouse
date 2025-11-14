#!/usr/bin/env python3
"""
Test script for MCP Planner Graph Integration - Phase 2 Step 1
Tests the MCP-enhanced planner graph functionality.
"""

import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.graphs.mcp_planner_graph import get_mcp_planner_graph, process_mcp_warehouse_query

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_mcp_planner_graph():
    """Test the MCP planner graph functionality."""
    logger.info("🧪 Testing MCP Planner Graph Integration - Phase 2 Step 1")
    
    try:
        # Test 1: Initialize MCP planner graph
        logger.info("📋 Test 1: Initializing MCP planner graph...")
        mcp_graph = await get_mcp_planner_graph()
        logger.info("✅ MCP planner graph initialized successfully")
        
        # Test 2: Test equipment query
        logger.info("📋 Test 2: Testing equipment query...")
        equipment_result = await process_mcp_warehouse_query(
            message="Show me the status of forklift FL-001",
            session_id="test_session_1"
        )
        logger.info(f"✅ Equipment query result: {equipment_result.get('intent', 'unknown')} intent")
        logger.info(f"   Response: {equipment_result.get('response', 'No response')[:100]}...")
        
        # Test 3: Test operations query
        logger.info("📋 Test 3: Testing operations query...")
        operations_result = await process_mcp_warehouse_query(
            message="How many workers are active in Zone A today?",
            session_id="test_session_2"
        )
        logger.info(f"✅ Operations query result: {operations_result.get('intent', 'unknown')} intent")
        logger.info(f"   Response: {operations_result.get('response', 'No response')[:100]}...")
        
        # Test 4: Test safety query
        logger.info("📋 Test 4: Testing safety query...")
        safety_result = await process_mcp_warehouse_query(
            message="Report a safety incident with temperature sensor TS-001",
            session_id="test_session_3"
        )
        logger.info(f"✅ Safety query result: {safety_result.get('intent', 'unknown')} intent")
        logger.info(f"   Response: {safety_result.get('response', 'No response')[:100]}...")
        
        # Test 5: Test MCP tool discovery
        logger.info("📋 Test 5: Testing MCP tool discovery...")
        if mcp_graph.tool_discovery:
            available_tools = await mcp_graph.tool_discovery.get_available_tools()
            logger.info(f"✅ MCP tool discovery found {len(available_tools)} tools")
            for tool in available_tools[:3]:  # Show first 3 tools
                logger.info(f"   - {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')[:50]}...")
        else:
            logger.warning("⚠️ MCP tool discovery not available")
        
        logger.info("🎉 All MCP Planner Graph tests completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ MCP Planner Graph test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    logger.info("🚀 Starting MCP Integration Phase 2 - Step 1 Tests")
    
    success = await test_mcp_planner_graph()
    
    if success:
        logger.info("✅ Phase 2 Step 1: MCP Planner Graph Integration - SUCCESS")
        logger.info("📋 Next Steps:")
        logger.info("   1. Create MCP-enabled agent implementations")
        logger.info("   2. Integrate MCP tools with existing agents")
        logger.info("   3. Test end-to-end MCP workflow")
    else:
        logger.error("❌ Phase 2 Step 1: MCP Planner Graph Integration - FAILED")
        logger.error("🔧 Please fix the issues before proceeding to next step")

if __name__ == "__main__":
    asyncio.run(main())
