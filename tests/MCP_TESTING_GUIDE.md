# MCP System Testing Guide

## Overview

This document provides comprehensive information about testing the Model Context Protocol (MCP) system in the Warehouse Operational Assistant. It covers unit tests, integration tests, performance tests, and the MCP Testing UI.

## Test Structure

### Unit Tests
- **Location**: `tests/test_mcp_system.py`
- **Purpose**: Test individual MCP components in isolation
- **Coverage**: MCP Server, MCP Client, MCP Adapters, Base Classes

### Integration Tests
- **Location**: `tests/integration/test_mcp_*.py`
- **Purpose**: Test MCP system integration and workflows
- **Coverage**: 
  - System integration (`test_mcp_system_integration.py`)
  - End-to-end workflows (`test_mcp_end_to_end.py`)
  - Agent workflows (`test_mcp_agent_workflows.py`)
  - Deployment integration (`test_mcp_deployment_integration.py`)
  - Security integration (`test_mcp_security_integration.py`)
  - Monitoring integration (`test_mcp_monitoring_integration.py`)
  - Rollback integration (`test_mcp_rollback_integration.py`)
  - Load testing (`test_mcp_load_testing.py`)

### Performance Tests
- **Location**: `tests/performance/test_mcp_performance.py`
- **Purpose**: Test MCP system performance and scalability
- **Coverage**: Load testing, stress testing, memory usage, concurrent execution

## Running Tests

### Run All MCP Tests
```bash
# Activate virtual environment
source env/bin/activate

# Run all MCP unit tests
pytest tests/test_mcp_system.py -v

# Run all MCP integration tests
pytest tests/integration/test_mcp_*.py -v

# Run all MCP performance tests
pytest tests/performance/test_mcp_performance.py -v

# Run all MCP tests
pytest tests/ -k mcp -v
```

### Run Specific Test Classes
```bash
# Test MCP Server only
pytest tests/test_mcp_system.py::TestMCPServer -v

# Test MCP Client only
pytest tests/test_mcp_system.py::TestMCPClient -v

# Test MCP Adapters only
pytest tests/test_mcp_system.py::TestMCPAdapter -v

# Test ERP Adapter only
pytest tests/test_mcp_system.py::TestMCPERPAdapter -v

# Test integration
pytest tests/test_mcp_system.py::TestMCPIntegration -v
```

### Run with Coverage
```bash
# Run tests with coverage report
pytest tests/test_mcp_system.py --cov=src.api.services.mcp --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Test Components

### 1. MCP Server Tests (`TestMCPServer`)

Tests the MCP server functionality:
- ✅ Server initialization
- ✅ Tool registration and unregistration
- ✅ Initialize request handling
- ✅ Tools list request handling
- ✅ Tools call request handling
- ✅ Invalid request handling
- ✅ Server info retrieval

**Example:**
```python
@pytest.mark.asyncio
async def test_tool_registration(self, mcp_server, sample_tool):
    """Test tool registration."""
    success = mcp_server.register_tool(sample_tool)
    assert success is True
    assert "test_tool" in mcp_server.tools
```

### 2. MCP Client Tests (`TestMCPClient`)

Tests the MCP client functionality:
- ✅ Client initialization
- ✅ HTTP server connection
- ✅ Server disconnection
- ✅ Client info retrieval

**Example:**
```python
@pytest.mark.asyncio
async def test_connect_http_server(self, mcp_client):
    """Test connecting to HTTP server."""
    success = await mcp_client.connect_server(
        "test-server",
        MCPConnectionType.HTTP,
        "http://localhost:8000"
    )
    assert success is True
```

### 3. MCP Adapter Tests (`TestMCPAdapter`)

Tests the base MCP adapter functionality:
- ✅ Adapter initialization
- ✅ Adapter connection and disconnection
- ✅ Health check
- ✅ Tool addition
- ✅ Resource addition
- ✅ Prompt addition
- ✅ Adapter info retrieval

**Example:**
```python
@pytest.mark.asyncio
async def test_adapter_connection(self, mock_adapter):
    """Test adapter connection."""
    success = await mock_adapter.connect()
    assert success is True
    assert mock_adapter.connected is True
```

### 4. ERP Adapter Tests (`TestMCPERPAdapter`)

Tests the ERP adapter implementation:
- ✅ ERP adapter initialization
- ✅ ERP adapter connection
- ✅ ERP tools setup
- ✅ ERP resources setup
- ✅ ERP prompts setup
- ✅ Customer info tool
- ✅ Create order tool
- ✅ Sync inventory tool

**Example:**
```python
@pytest.mark.asyncio
async def test_get_customer_info_tool(self, mock_erp_adapter):
    """Test get customer info tool."""
    await mock_erp_adapter.initialize()
    await mock_erp_adapter.connect()
    
    result = await mock_erp_adapter._handle_get_customer_info({"customer_id": "1"})
    assert result["success"] is True
```

### 5. Integration Tests (`TestMCPIntegration`)

Tests integration between MCP components:
- ✅ Server-client integration
- ✅ Adapter-server integration

**Example:**
```python
@pytest.mark.asyncio
async def test_server_client_integration(self):
    """Test integration between MCP server and client."""
    server = MCPServer(name="test-server", version="1.0.0")
    # ... test integration
```

## MCP Testing UI

The MCP Testing UI (`EnhancedMCPTestingPanel`) provides an interactive interface for testing the MCP system:

### Features
- **Status & Discovery Tab**: View MCP framework status and discover tools
- **Tool Search Tab**: Search for specific tools with detailed results
- **Workflow Testing Tab**: Test complete workflows with sample messages
- **Execution History Tab**: View execution history and performance metrics

### Access
- **URL**: `http://localhost:3001/mcp-test`
- **Navigation**: Available via the main navigation menu

### Usage
1. **Check Status**: View MCP framework status and service health
2. **Discover Tools**: Refresh tool discovery to see all available tools
3. **Search Tools**: Search for specific tools by name, category, or description
4. **Test Workflows**: Send test messages to verify end-to-end workflows
5. **View History**: Review execution history and performance metrics

## Test Data

### Mock Data
Tests use mock data and fixtures to avoid dependencies on external services:
- Mock ERP adapter responses
- Mock HTTP server responses
- Mock tool handlers
- Mock database connections

### Test Fixtures
Common fixtures available:
- `mcp_server`: MCP server instance
- `mcp_client`: MCP client instance
- `sample_tool`: Sample tool for testing
- `adapter_config`: Adapter configuration
- `mock_adapter`: Mock adapter instance
- `erp_config`: ERP adapter configuration
- `mock_erp_adapter`: Mock ERP adapter instance

## Test Coverage

### Current Coverage
- **MCP Server**: 100% coverage
- **MCP Client**: 95% coverage
- **MCP Adapters**: 90% coverage
- **ERP Adapter**: 85% coverage
- **Integration Tests**: 80% coverage

### Coverage Goals
- **Target**: 90%+ coverage for all MCP components
- **Critical Paths**: 100% coverage
- **Edge Cases**: 85%+ coverage

## Troubleshooting

### Common Issues

#### 1. Import Errors
**Error**: `ModuleNotFoundError: No module named 'src.api.services.mcp'`
**Solution**: Ensure virtual environment is activated and dependencies are installed:
```bash
source env/bin/activate
pip install -r requirements.txt
```

#### 2. Async Test Failures
**Error**: `RuntimeError: Event loop is closed`
**Solution**: Ensure async tests use `@pytest.mark.asyncio` decorator and proper event loop handling.

#### 3. Mock Connection Failures
**Error**: `ConnectionError` in tests
**Solution**: Ensure all external connections are properly mocked using `unittest.mock.patch`.

#### 4. Test Timeout
**Error**: `pytest timeout`
**Solution**: Increase timeout or optimize test execution:
```bash
pytest tests/test_mcp_system.py --timeout=30
```

## Best Practices

### Writing MCP Tests

1. **Use Fixtures**: Create reusable fixtures for common test objects
2. **Mock External Dependencies**: Mock all external services and databases
3. **Test Async Code Properly**: Use `@pytest.mark.asyncio` for async tests
4. **Test Error Cases**: Include tests for error handling and edge cases
5. **Use Descriptive Names**: Use clear, descriptive test names
6. **Keep Tests Isolated**: Each test should be independent and not rely on others
7. **Test Both Success and Failure**: Test both happy path and error scenarios

### Example Test Structure
```python
class TestMCPComponent:
    """Test cases for MCP Component."""
    
    @pytest.fixture
    def component(self):
        """Create component instance for testing."""
        return MCPComponent()
    
    @pytest.mark.asyncio
    async def test_component_functionality(self, component):
        """Test component functionality."""
        # Arrange
        test_input = "test"
        
        # Act
        result = await component.process(test_input)
        
        # Assert
        assert result is not None
        assert result["status"] == "success"
```

## Continuous Integration

### CI/CD Integration
MCP tests are automatically run in CI/CD pipeline:
- **On Pull Request**: All unit and integration tests
- **On Merge**: Full test suite including performance tests
- **Nightly**: Extended test suite with load testing

### Test Reports
Test results are available in:
- **CI/CD Dashboard**: Real-time test results
- **Coverage Reports**: HTML coverage reports
- **Test Artifacts**: Test logs and reports

## Related Documentation

- **MCP Integration Guide**: `docs/architecture/mcp-integration.md`
- **MCP API Reference**: `docs/architecture/mcp-api-reference.md`
- **MCP Deployment Guide**: `docs/architecture/mcp-deployment-guide.md`
- **MCP Migration Guide**: `docs/architecture/mcp-migration-guide.md`

## Support

For MCP testing support:
- **Issues**: [GitHub Issues](https://github.com/T-DevH/Multi-Agent-Intelligent-Warehouse/issues)
- **Documentation**: `docs/architecture/mcp-*.md`
- **API Documentation**: `http://localhost:8001/docs`

---

**Last Updated**: 2025-01-XX  
**Test Coverage**: 90%+  
**Status**: ✅ Active and Maintained

