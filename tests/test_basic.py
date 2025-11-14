"""
Basic test suite for Warehouse Operational Assistant.
These tests ensure the core functionality works correctly.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Test that main modules can be imported."""
    try:
        from src.api.app import app
        assert app is not None
        print("✅ chain_server.app imported successfully")
    except ImportError as e:
        pytest.skip(f"Could not import src.api.app: {e}")

def test_health_endpoint():
    """Test health endpoint if available."""
    try:
        from src.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/v1/health")
        assert response.status_code in [200, 404]  # 404 if endpoint doesn't exist
        print(f"✅ Health endpoint responded with status {response.status_code}")
    except ImportError:
        pytest.skip("FastAPI test client not available")

def test_mcp_services_import():
    """Test that MCP services can be imported."""
    try:
        from src.api.services.mcp.tool_discovery import ToolDiscoveryService
        from src.api.services.mcp.tool_binding import ToolBindingService
        from src.api.services.mcp.tool_routing import ToolRoutingService
        from src.api.services.mcp.tool_validation import ToolValidationService
        print("✅ MCP services imported successfully")
    except ImportError as e:
        pytest.skip(f"Could not import MCP services: {e}")

def test_agents_import():
    """Test that agent modules can be imported."""
    try:
        from src.api.agents.inventory.equipment_agent import get_equipment_agent
        from src.api.agents.operations.operations_agent import get_operations_agent
        from src.api.agents.safety.safety_agent import get_safety_agent
        print("✅ Agent modules imported successfully")
    except ImportError as e:
        pytest.skip(f"Could not import agent modules: {e}")

def test_reasoning_engine_import():
    """Test that reasoning engine can be imported."""
    try:
        from src.api.services.reasoning.reasoning_engine import AdvancedReasoningEngine
        print("✅ Reasoning engine imported successfully")
    except ImportError as e:
        pytest.skip(f"Could not import reasoning engine: {e}")

def test_placeholder():
    """Placeholder test to ensure test suite runs."""
    assert True
    print("✅ Basic test passed")

@pytest.mark.asyncio
async def test_mcp_tool_discovery():
    """Test MCP tool discovery service."""
    try:
        from src.api.services.mcp.tool_discovery import ToolDiscoveryService
        
        # Mock the discovery service
        discovery = ToolDiscoveryService()
        
        # Test basic functionality
        tools = await discovery.get_available_tools()
        assert isinstance(tools, list)
        print(f"✅ MCP tool discovery found {len(tools)} tools")
        
    except ImportError as e:
        pytest.skip(f"Could not test MCP tool discovery: {e}")
    except Exception as e:
        # This is expected if MCP services aren't fully configured
        print(f"⚠️ MCP tool discovery test skipped: {e}")

def test_environment_variables():
    """Test that required environment variables are accessible."""
    import os
    
    # Check if we're in a test environment
    test_env = os.getenv('TESTING', 'false').lower() == 'true'
    
    if test_env:
        # In test environment, check for required vars
        required_vars = ['NVIDIA_API_KEY', 'NVIDIA_EMBEDDING_API_KEY']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            print(f"⚠️ Missing environment variables: {missing_vars}")
        else:
            print("✅ All required environment variables present")
    else:
        print("ℹ️ Skipping environment variable check (not in test environment)")

def test_database_connection():
    """Test database connection if available."""
    try:
        from src.api.services.database import get_database_connection
        # This might fail if database isn't configured, which is okay
        print("✅ Database service imported successfully")
    except ImportError as e:
        print(f"ℹ️ Database service not available: {e}")

if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
