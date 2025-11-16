"""
Tests for the MCP (Model Context Protocol) system.

This module contains comprehensive tests for the MCP server, client, and adapter components.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.api.services.mcp.server import MCPServer, MCPTool, MCPToolType
from src.api.services.mcp.client import MCPClient, MCPConnectionType
from src.api.services.mcp.base import MCPAdapter, AdapterConfig, AdapterType, ToolConfig, ToolCategory
from src.api.services.mcp.adapters.erp_adapter import MCPERPAdapter


class TestMCPServer:
    """Test cases for the MCP Server."""
    
    @pytest.fixture
    def mcp_server(self):
        """Create an MCP server instance for testing."""
        return MCPServer(name="test-server", version="1.0.0")
    
    @pytest.fixture
    def sample_tool(self):
        """Create a sample tool for testing."""
        async def test_handler(arguments):
            return {"result": f"Processed: {arguments}"}
        
        return MCPTool(
            name="test_tool",
            description="A test tool",
            tool_type=MCPToolType.FUNCTION,
            parameters={"input": {"type": "string"}},
            handler=test_handler
        )
    
    @pytest.mark.asyncio
    async def test_server_initialization(self, mcp_server):
        """Test server initialization."""
        assert mcp_server.name == "test-server"
        assert mcp_server.version == "1.0.0"
        assert len(mcp_server.tools) == 0
        assert len(mcp_server.resources) == 0
        assert len(mcp_server.prompts) == 0
    
    @pytest.mark.asyncio
    async def test_tool_registration(self, mcp_server, sample_tool):
        """Test tool registration."""
        success = mcp_server.register_tool(sample_tool)
        assert success is True
        assert "test_tool" in mcp_server.tools
        assert mcp_server.tools["test_tool"] == sample_tool
    
    @pytest.mark.asyncio
    async def test_tool_unregistration(self, mcp_server, sample_tool):
        """Test tool unregistration."""
        mcp_server.register_tool(sample_tool)
        success = mcp_server.unregister_tool("test_tool")
        assert success is True
        assert "test_tool" not in mcp_server.tools
    
    @pytest.mark.asyncio
    async def test_initialize_request(self, mcp_server):
        """Test initialize request handling."""
        request = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }
        
        response = await mcp_server.handle_message(request)
        response_data = json.loads(response)
        
        assert response_data["id"] == "1"
        assert "result" in response_data
        assert response_data["result"]["protocolVersion"] == "2024-11-05"
        assert response_data["result"]["serverInfo"]["name"] == "test-server"
    
    @pytest.mark.asyncio
    async def test_tools_list_request(self, mcp_server, sample_tool):
        """Test tools/list request handling."""
        mcp_server.register_tool(sample_tool)
        
        request = {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tools/list",
            "params": {}
        }
        
        response = await mcp_server.handle_message(request)
        response_data = json.loads(response)
        
        assert response_data["id"] == "2"
        assert "result" in response_data
        assert len(response_data["result"]["tools"]) == 1
        assert response_data["result"]["tools"][0]["name"] == "test_tool"
    
    @pytest.mark.asyncio
    async def test_tools_call_request(self, mcp_server, sample_tool):
        """Test tools/call request handling."""
        mcp_server.register_tool(sample_tool)
        
        request = {
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tools/call",
            "params": {
                "name": "test_tool",
                "arguments": {"input": "test input"}
            }
        }
        
        response = await mcp_server.handle_message(request)
        response_data = json.loads(response)
        
        assert response_data["id"] == "3"
        assert "result" in response_data
        assert "Processed: {'input': 'test input'}" in response_data["result"]["content"][0]["text"]
    
    @pytest.mark.asyncio
    async def test_invalid_request(self, mcp_server):
        """Test handling of invalid requests."""
        request = {
            "jsonrpc": "2.0",
            "id": "4",
            "method": "invalid_method",
            "params": {}
        }
        
        response = await mcp_server.handle_message(request)
        response_data = json.loads(response)
        
        assert response_data["id"] == "4"
        assert "error" in response_data
        assert response_data["error"]["code"] == -32601  # Method not found
    
    def test_server_info(self, mcp_server, sample_tool):
        """Test server info retrieval."""
        mcp_server.register_tool(sample_tool)
        mcp_server.register_resource("test_resource", {"data": "test"})
        mcp_server.register_prompt("test_prompt", {"template": "test"})
        
        info = mcp_server.get_server_info()
        
        assert info["name"] == "test-server"
        assert info["version"] == "1.0.0"
        assert info["tools_count"] == 1
        assert info["resources_count"] == 1
        assert info["prompts_count"] == 1


class TestMCPClient:
    """Test cases for the MCP Client."""
    
    @pytest.fixture
    def mcp_client(self):
        """Create an MCP client instance for testing."""
        return MCPClient(client_name="test-client", version="1.0.0")
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, mcp_client):
        """Test client initialization."""
        assert mcp_client.client_name == "test-client"
        assert mcp_client.version == "1.0.0"
        assert len(mcp_client.servers) == 0
        assert len(mcp_client.tools) == 0
        assert len(mcp_client.resources) == 0
        assert len(mcp_client.prompts) == 0
    
    @pytest.mark.asyncio
    async def test_connect_http_server(self, mcp_client):
        """Test connecting to HTTP server."""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value = AsyncMock()
            
            # Mock the HTTP request response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "test-server", "version": "1.0.0"}
                }
            }
            
            mock_session.return_value.post.return_value.__aenter__.return_value = mock_response
            
            success = await mcp_client.connect_server(
                "test-server",
                MCPConnectionType.HTTP,
                "http://localhost:8000"
            )
            
            assert success is True
            assert "test-server" in mcp_client.servers
            assert mcp_client.servers["test-server"]["connected"] is True
    
    @pytest.mark.asyncio
    async def test_disconnect_server(self, mcp_client):
        """Test disconnecting from server."""
        # Add a mock server
        mcp_client.servers["test-server"] = {
            "name": "test-server",
            "connection_type": MCPConnectionType.HTTP,
            "endpoint": "http://localhost:8000",
            "connected": True,
            "session": AsyncMock()
        }
        
        success = await mcp_client.disconnect_server("test-server")
        
        assert success is True
        assert "test-server" not in mcp_client.servers
    
    def test_client_info(self, mcp_client):
        """Test client info retrieval."""
        info = mcp_client.get_client_info()
        
        assert info["name"] == "test-client"
        assert info["version"] == "1.0.0"
        assert info["connected_servers"] == 0
        assert info["available_tools"] == 0
        assert info["available_resources"] == 0
        assert info["available_prompts"] == 0


class TestMCPAdapter:
    """Test cases for the MCP Adapter base class."""
    
    @pytest.fixture
    def adapter_config(self):
        """Create an adapter config for testing."""
        return AdapterConfig(
            name="test-adapter",
            adapter_type=AdapterType.ERP,
            endpoint="http://localhost:8000",
            connection_type=MCPConnectionType.HTTP
        )
    
    @pytest.fixture
    def mock_adapter(self, adapter_config):
        """Create a mock adapter for testing."""
        class MockAdapter(MCPAdapter):
            async def initialize(self):
                return True
            
            async def connect(self):
                self.connected = True
                return True
            
            async def disconnect(self):
                self.connected = False
                return True
            
            async def health_check(self):
                return {
                    "status": "healthy",
                    "message": "Mock adapter is healthy",
                    "timestamp": datetime.utcnow().isoformat()
                }
        
        return MockAdapter(adapter_config)
    
    @pytest.mark.asyncio
    async def test_adapter_initialization(self, mock_adapter):
        """Test adapter initialization."""
        success = await mock_adapter.initialize()
        assert success is True
    
    @pytest.mark.asyncio
    async def test_adapter_connection(self, mock_adapter):
        """Test adapter connection."""
        success = await mock_adapter.connect()
        assert success is True
        assert mock_adapter.connected is True
    
    @pytest.mark.asyncio
    async def test_adapter_disconnection(self, mock_adapter):
        """Test adapter disconnection."""
        await mock_adapter.connect()
        success = await mock_adapter.disconnect()
        assert success is True
        assert mock_adapter.connected is False
    
    @pytest.mark.asyncio
    async def test_adapter_health_check(self, mock_adapter):
        """Test adapter health check."""
        health = await mock_adapter.health_check()
        assert health["status"] == "healthy"
        assert "message" in health
        assert "timestamp" in health
    
    def test_add_tool(self, mock_adapter):
        """Test adding a tool to adapter."""
        tool_config = ToolConfig(
            name="test_tool",
            description="A test tool",
            category=ToolCategory.DATA_ACCESS,
            parameters={"input": {"type": "string"}}
        )
        
        success = mock_adapter.add_tool(tool_config)
        assert success is True
        assert "test_tool" in mock_adapter.tools
    
    def test_add_resource(self, mock_adapter):
        """Test adding a resource to adapter."""
        success = mock_adapter.add_resource("test_resource", {"data": "test"})
        assert success is True
        assert "test_resource" in mock_adapter.resources
    
    def test_add_prompt(self, mock_adapter):
        """Test adding a prompt to adapter."""
        success = mock_adapter.add_prompt("test_prompt", "Test template {arg}")
        assert success is True
        assert "test_prompt" in mock_adapter.prompts
    
    def test_adapter_info(self, mock_adapter):
        """Test adapter info retrieval."""
        info = mock_adapter.get_adapter_info()
        
        assert info["name"] == "test-adapter"
        assert info["type"] == "erp"
        assert info["connected"] is False
        assert info["tools_count"] == 0
        assert info["resources_count"] == 0
        assert info["prompts_count"] == 0


class TestMCPERPAdapter:
    """Test cases for the MCP ERP Adapter."""
    
    @pytest.fixture
    def erp_config(self):
        """Create ERP adapter config for testing."""
        return AdapterConfig(
            name="test-erp",
            adapter_type=AdapterType.ERP,
            endpoint="http://localhost:8000",
            connection_type=MCPConnectionType.HTTP,
            credentials={"api_key": "test-key"}
        )
    
    @pytest.fixture
    def mock_erp_adapter(self, erp_config):
        """Create a mock ERP adapter for testing."""
        with patch('src.api.services.mcp.adapters.erp_adapter.ERPIntegrationService') as mock_base:
            mock_instance = AsyncMock()
            mock_instance.initialize.return_value = True
            mock_instance.connect.return_value = True
            mock_instance.disconnect.return_value = True
            mock_instance.health_check.return_value = {"status": "healthy", "message": "OK"}
            mock_instance.get_customer.return_value = {"id": "1", "name": "Test Customer"}
            mock_instance.search_customers.return_value = [{"id": "1", "name": "Test Customer"}]
            mock_instance.get_order.return_value = {"id": "1", "customer_id": "1", "status": "pending"}
            mock_instance.create_order.return_value = "order-123"
            mock_instance.update_order_status.return_value = True
            mock_instance.sync_inventory.return_value = {"synced_items": ["item1", "item2"]}
            mock_instance.get_inventory_levels.return_value = [{"item_id": "1", "quantity": 100}]
            mock_instance.get_financial_summary.return_value = {"revenue": 1000, "profit": 200}
            mock_instance.get_sales_report.return_value = {"total_sales": 1000, "period": "2024-01"}
            
            mock_base.return_value = mock_instance
            
            adapter = MCPERPAdapter(erp_config)
            return adapter
    
    @pytest.mark.asyncio
    async def test_erp_adapter_initialization(self, mock_erp_adapter):
        """Test ERP adapter initialization."""
        success = await mock_erp_adapter.initialize()
        assert success is True
        assert mock_erp_adapter.erp_adapter is not None
    
    @pytest.mark.asyncio
    async def test_erp_adapter_connection(self, mock_erp_adapter):
        """Test ERP adapter connection."""
        await mock_erp_adapter.initialize()
        success = await mock_erp_adapter.connect()
        assert success is True
        assert mock_erp_adapter.connected is True
    
    @pytest.mark.asyncio
    async def test_erp_tools_setup(self, mock_erp_adapter):
        """Test ERP adapter tools setup."""
        await mock_erp_adapter.initialize()
        
        # Check that tools are set up
        assert len(mock_erp_adapter.tools) > 0
        assert "get_customer_info" in mock_erp_adapter.tools
        assert "create_order" in mock_erp_adapter.tools
        assert "sync_inventory" in mock_erp_adapter.tools
    
    @pytest.mark.asyncio
    async def test_erp_resources_setup(self, mock_erp_adapter):
        """Test ERP adapter resources setup."""
        await mock_erp_adapter.initialize()
        
        # Check that resources are set up
        assert len(mock_erp_adapter.resources) > 0
        assert "erp_config" in mock_erp_adapter.resources
        assert "supported_operations" in mock_erp_adapter.resources
    
    @pytest.mark.asyncio
    async def test_erp_prompts_setup(self, mock_erp_adapter):
        """Test ERP adapter prompts setup."""
        await mock_erp_adapter.initialize()
        
        # Check that prompts are set up
        assert len(mock_erp_adapter.prompts) > 0
        assert "customer_query_prompt" in mock_erp_adapter.prompts
        assert "order_analysis_prompt" in mock_erp_adapter.prompts
    
    @pytest.mark.asyncio
    async def test_get_customer_info_tool(self, mock_erp_adapter):
        """Test get customer info tool."""
        await mock_erp_adapter.initialize()
        await mock_erp_adapter.connect()
        
        result = await mock_erp_adapter._handle_get_customer_info({"customer_id": "1"})
        
        assert result["success"] is True
        assert "data" in result
        assert result["data"]["id"] == "1"
    
    @pytest.mark.asyncio
    async def test_create_order_tool(self, mock_erp_adapter):
        """Test create order tool."""
        await mock_erp_adapter.initialize()
        await mock_erp_adapter.connect()
        
        result = await mock_erp_adapter._handle_create_order({
            "customer_id": "1",
            "items": [{"product_id": "prod1", "quantity": 2, "price": 10.0}],
            "notes": "Test order"
        })
        
        assert result["success"] is True
        assert "order_id" in result
        assert result["order_id"] == "order-123"
    
    @pytest.mark.asyncio
    async def test_sync_inventory_tool(self, mock_erp_adapter):
        """Test sync inventory tool."""
        await mock_erp_adapter.initialize()
        await mock_erp_adapter.connect()
        
        result = await mock_erp_adapter._handle_sync_inventory({"item_ids": ["item1", "item2"]})
        
        assert result["success"] is True
        assert "data" in result
        assert result["items_synced"] == 2


# Integration tests
class TestMCPIntegration:
    """Integration tests for the MCP system."""
    
    @pytest.mark.asyncio
    async def test_server_client_integration(self):
        """Test integration between MCP server and client."""
        # Create server
        server = MCPServer(name="test-server", version="1.0.0")
        
        # Add a test tool
        async def test_handler(arguments):
            return f"Processed: {arguments['input']}"
        
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            tool_type=MCPToolType.FUNCTION,
            parameters={"input": {"type": "string"}},
            handler=test_handler
        )
        server.register_tool(tool)
        
        # Test tool execution
        result = await server.execute_tool("test_tool", {"input": "test data"})
        assert result == "Processed: test data"
        
        # Test tools list
        tools = server.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"
    
    @pytest.mark.asyncio
    async def test_adapter_server_integration(self):
        """Test integration between adapter and server."""
        # Create server
        server = MCPServer(name="test-server", version="1.0.0")
        
        # Create mock adapter
        config = AdapterConfig(
            name="test-adapter",
            adapter_type=AdapterType.ERP,
            endpoint="http://localhost:8000",
            connection_type=MCPConnectionType.HTTP
        )
        
        class MockAdapter(MCPAdapter):
            async def initialize(self):
                return True
            
            async def connect(self):
                self.connected = True
                return True
            
            async def disconnect(self):
                self.connected = False
                return True
            
            async def health_check(self):
                return {"status": "healthy", "message": "OK"}
        
        adapter = MockAdapter(config)
        await adapter.initialize()
        
        # Add a tool to adapter
        tool_config = ToolConfig(
            name="adapter_tool",
            description="Adapter tool",
            category=ToolCategory.DATA_ACCESS,
            parameters={"input": {"type": "string"}}
        )
        adapter.add_tool(tool_config)
        
        # Register adapter with server
        success = await adapter.register_tools(server)
        assert success is True
        
        # Check that tool is registered
        tools = server.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "adapter_tool"


# Test configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test markers
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.unit,
]
