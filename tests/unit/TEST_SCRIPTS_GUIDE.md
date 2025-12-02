# Unit Test Scripts Usage Guide

**Last Updated:** 2025-01-XX  
**Purpose:** Guide for running and using unit test scripts in the Warehouse Operational Assistant

---

## Overview

This directory contains unit test scripts for testing various components of the Warehouse Operational Assistant. All tests use shared configuration and utilities for consistency and maintainability.

---

## Quick Start

### Prerequisites

1. **Python Environment**
   ```bash
   # Activate virtual environment
   source env/bin/activate
   ```

2. **Environment Variables** (Optional - defaults provided)
   ```bash
   export API_BASE_URL="http://localhost:8001"  # Default
   export TEST_TIMEOUT="180"  # Default: 180 seconds
   export NVIDIA_API_KEY="your_key_here"  # Required for NVIDIA tests
   ```

3. **Services Running**
   - Backend API server (default: `http://localhost:8001`)
   - PostgreSQL/TimescaleDB (default: `localhost:5435`)
   - Redis (optional, for cache tests)
   - Milvus (optional, for vector tests)

---

## Available Test Scripts

### 1. **test_all_agents.py** - Comprehensive Agent Testing
Tests all warehouse agents (Operations, Safety, Memory Manager) and full integration.

```bash
python tests/unit/test_all_agents.py
```

**What it tests:**
- Operations Coordination Agent
- Safety & Compliance Agent
- Memory Manager
- Full integration with NVIDIA NIMs
- API endpoints

**Expected runtime:** 2-5 minutes

---

### 2. **test_nvidia_llm.py** - NVIDIA LLM API Testing
Tests NVIDIA NIM LLM and embedding APIs.

```bash
python tests/unit/test_nvidia_llm.py
```

**What it tests:**
- LLM generation
- Embedding generation
- API connectivity

**Requirements:** `NVIDIA_API_KEY` environment variable

**Expected runtime:** 30-60 seconds

---

### 3. **test_guardrails.py** - NeMo Guardrails Testing
Tests content safety, security, and compliance guardrails.

```bash
python tests/unit/test_guardrails.py
```

**What it tests:**
- Jailbreak attempt detection
- Safety violation detection
- Security violation detection
- Compliance violation detection
- Off-topic query handling
- Performance with concurrent requests

**Expected runtime:** 1-2 minutes

---

### 4. **test_db_connection.py** - Database Connection Testing
Tests database connectivity and authentication.

```bash
python tests/unit/test_db_connection.py
```

**What it tests:**
- SQL Retriever initialization
- Database queries
- User service authentication

**Requirements:** PostgreSQL/TimescaleDB running

**Expected runtime:** 10-20 seconds

---

### 5. **test_enhanced_retrieval.py** - Vector Search Testing
Tests enhanced vector search and retrieval capabilities.

```bash
python tests/unit/test_enhanced_retrieval.py
```

**What it tests:**
- Chunking service
- Enhanced vector retrieval
- Hybrid retrieval (SQL + Vector)
- Evidence scoring
- Clarifying questions

**Requirements:** Milvus running (optional - will skip if unavailable)

**Expected runtime:** 1-3 minutes

---

### 6. **test_mcp_planner_integration.py** - MCP Planner Testing
Tests the MCP-enabled planner graph functionality.

```bash
python tests/unit/test_mcp_planner_integration.py
```

**What it tests:**
- MCP planner graph initialization
- Equipment queries
- Operations queries
- Safety queries
- MCP tool discovery

**Expected runtime:** 1-2 minutes

---

### 7. **test_nvidia_integration.py** - Full NVIDIA Integration Testing
Tests complete NVIDIA NIM integration with inventory queries.

```bash
python tests/unit/test_nvidia_integration.py
```

**What it tests:**
- NIM Client health check
- Inventory Intelligence Agent
- Sample inventory queries
- API endpoint integration

**Requirements:** `NVIDIA_API_KEY` environment variable

**Expected runtime:** 2-3 minutes

---

### 8. **test_document_pipeline.py** - Document Processing Testing
Tests the complete document extraction pipeline (5 stages).

```bash
python tests/unit/test_document_pipeline.py
```

**What it tests:**
- Stage 1: NeMo Retriever Preprocessing
- Stage 2: NeMo OCR Service
- Stage 3: Small LLM Processing
- Stage 4: Large LLM Judge Validation
- Stage 5: Intelligent Router

**Requirements:** 
- Test file: `test_invoice.png` (in project root, `data/sample/`, or `tests/fixtures/`)
- NVIDIA API keys for all services

**Expected runtime:** 3-5 minutes

---

### 9. **test_caching_demo.py** - Cache System Testing
Tests Redis caching system with SQL results, evidence packs, and monitoring.

```bash
python tests/unit/test_caching_demo.py
```

**What it tests:**
- Redis cache service
- Cache manager
- Cache integration
- Cache monitoring

**Requirements:** Redis running (optional - will skip if unavailable)

**Expected runtime:** 1-2 minutes

---

### 10. **test_prompt_injection_protection.py** - Security Testing
Tests prompt injection protection (pytest-based).

```bash
pytest tests/unit/test_prompt_injection_protection.py -v
```

**What it tests:**
- Template injection prevention
- Variable access protection
- Control character handling
- Safe prompt formatting

**Expected runtime:** 5-10 seconds

---

### 11. **test_prompt_injection_simple.py** - Security Testing (Standalone)
Simple standalone test for prompt injection protection (no pytest required).

```bash
python tests/unit/test_prompt_injection_simple.py
```

**What it tests:**
- Same as `test_prompt_injection_protection.py` but standalone

**Expected runtime:** 5-10 seconds

---

### 12. **test_response_quality_demo.py** - Response Quality Testing
Tests response quality control system.

```bash
python tests/unit/test_response_quality_demo.py
```

**What it tests:**
- Response validator
- Response enhancer
- Chat response enhancement
- UX analytics

**Expected runtime:** 1-2 minutes

---

### 13. **test_evidence_scoring_demo.py** - Evidence Scoring Testing
Tests evidence scoring and clarifying questions functionality.

```bash
python tests/unit/test_evidence_scoring_demo.py
```

**What it tests:**
- Evidence scoring engine
- Clarifying questions engine
- Integrated workflow

**Expected runtime:** 30-60 seconds

---

### 14. **test_chunking_demo.py** - Chunking Service Demo
Demonstrates the chunking service functionality.

```bash
python tests/unit/test_chunking_demo.py
```

**What it tests:**
- Document chunking
- Chunk statistics
- Quality scoring

**Expected runtime:** 5-10 seconds

---

## Configuration

### Shared Configuration Module

All tests use `tests/unit/test_config.py` for centralized configuration:

```python
# API Configuration
API_BASE_URL = "http://localhost:8001"  # Override with env var
CHAT_ENDPOINT = f"{API_BASE_URL}/api/v1/chat"
HEALTH_ENDPOINT = f"{API_BASE_URL}/api/v1/health/simple"

# Timeout Configuration (seconds)
DEFAULT_TIMEOUT = 180  # 3 minutes for complex queries
GUARDRAILS_TIMEOUT = 60  # 1 minute for guardrails
SIMPLE_QUERY_TIMEOUT = 30  # 30 seconds for simple queries
```

### Environment Variables

You can override defaults using environment variables:

```bash
export API_BASE_URL="http://localhost:8001"
export TEST_TIMEOUT="180"
export GUARDRAILS_TIMEOUT="60"
export NVIDIA_API_KEY="your_key_here"
export POSTGRES_PASSWORD="your_password"
```

---

## Shared Utilities

All tests can use utilities from `tests/unit/test_utils.py`:

- `cleanup_async_resource()` - Safe async resource cleanup
- `get_test_file_path()` - Find test files in common locations
- `require_env_var()` - Validate environment variables
- `create_test_session_id()` - Generate unique session IDs

---

## Running Tests

### Individual Test Scripts

```bash
# Run a specific test
python tests/unit/test_all_agents.py

# Run with verbose output
python tests/unit/test_guardrails.py
```

### Using Pytest (for pytest-based tests)

```bash
# Run all pytest tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_prompt_injection_protection.py -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html
```

### Running All Tests

```bash
# Run all standalone test scripts
for test in tests/unit/test_*.py; do
    if [[ ! "$test" =~ "pytest" ]]; then
        echo "Running $test..."
        python "$test"
    fi
done
```

---

## Troubleshooting

### Common Issues

1. **Import Errors**
   - **Problem:** `ModuleNotFoundError` or import errors
   - **Solution:** Ensure you're running from project root and virtual environment is activated
   ```bash
   cd /path/to/warehouse-operational-assistant
   source env/bin/activate
   ```

2. **Connection Errors**
   - **Problem:** Cannot connect to API or database
   - **Solution:** 
     - Check if backend server is running: `curl http://localhost:8001/api/v1/health/simple`
     - Verify database is running: `psql -h localhost -p 5435 -U warehouse -d warehouse`
     - Check environment variables match your setup

3. **Timeout Errors**
   - **Problem:** Tests timing out
   - **Solution:** Increase timeout via environment variable
   ```bash
   export TEST_TIMEOUT="300"  # 5 minutes
   ```

4. **Missing Test Files**
   - **Problem:** `test_invoice.png` not found
   - **Solution:** Place test file in one of these locations:
     - Project root: `test_invoice.png`
     - `data/sample/test_invoice.png`
     - `tests/fixtures/test_invoice.png`

5. **NVIDIA API Errors**
   - **Problem:** NVIDIA API key not configured
   - **Solution:** Set `NVIDIA_API_KEY` environment variable
   ```bash
   export NVIDIA_API_KEY="your_key_here"
   ```

---

## Test Results

### Understanding Test Output

- ✅ **PASS** - Test completed successfully
- ❌ **FAIL** - Test failed (check error messages)
- ⚠️ **WARNING** - Test completed but with warnings
- ⏱️ **TIMEOUT** - Test exceeded timeout limit

### Example Output

```
🚀 Starting Chat Router & Agent Tests...
   Session ID: test_session_20250101_120000
   API Base: http://localhost:8001/api/v1

Testing EQUIPMENT agent...
  → Show me the status of forklift FL-01...
✅ Equipment Query: PASSED

📊 OVERALL STATISTICS:
   Total Tests: 20
   Successful Routes: 18/20 (90.0%)
   Average Latency: 2.45s
```

---

## Best Practices

1. **Run tests before committing code**
   ```bash
   python tests/unit/test_all_agents.py
   ```

2. **Use appropriate timeouts**
   - Simple queries: 30s
   - Complex queries: 180s
   - Guardrails: 60s

3. **Check service health first**
   ```bash
   curl http://localhost:8001/api/v1/health/simple
   ```

4. **Run tests in order of dependency**
   - Start with `test_db_connection.py`
   - Then `test_nvidia_llm.py`
   - Finally integration tests

5. **Review test logs**
   - Check for warnings and errors
   - Verify expected behavior
   - Note any performance issues

---

## Additional Resources

- **Test Configuration:** `tests/unit/test_config.py`
- **Test Utilities:** `tests/unit/test_utils.py`
- **Pytest Fixtures:** `tests/conftest.py`
- **Integration Tests:** `tests/integration/`
- **Performance Tests:** `tests/performance/`

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review test logs for error messages
3. Verify all services are running
4. Check environment variables are set correctly

---

**Last Updated:** 2025-01-XX  
**Maintained by:** Development Team

