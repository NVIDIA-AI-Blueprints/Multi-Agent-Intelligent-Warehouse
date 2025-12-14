"""
Pytest configuration and fixtures for unit tests.

Provides shared fixtures and configuration for pytest-based tests.
"""

import pytest
import asyncio
import os
from pathlib import Path
from typing import Generator

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Get API base URL from environment."""
    return os.getenv("API_BASE_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def chat_endpoint(api_base_url: str) -> str:
    """Get chat endpoint URL."""
    return f"{api_base_url}/api/v1/chat"


@pytest.fixture(scope="session")
def health_endpoint(api_base_url: str) -> str:
    """Get health endpoint URL."""
    return f"{api_base_url}/api/v1/health/simple"


@pytest.fixture(scope="session")
def test_timeout() -> int:
    """Get test timeout from environment."""
    return int(os.getenv("TEST_TIMEOUT", "180"))


@pytest.fixture(scope="session")
def guardrails_timeout() -> int:
    """Get guardrails timeout from environment."""
    return int(os.getenv("GUARDRAILS_TIMEOUT", "60"))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create event loop for async tests.
    
    This fixture ensures that async tests have a proper event loop.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def test_session_id() -> str:
    """Generate a unique test session ID."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"test_session_{timestamp}"


@pytest.fixture(scope="function")
def nvidia_api_key() -> str:
    """Get NVIDIA API key from environment."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key or api_key == "your_nvidia_api_key_here":
        pytest.skip("NVIDIA_API_KEY not configured")
    return api_key


@pytest.fixture(scope="function")
def test_data_dir(project_root: Path) -> Path:
    """Get test data directory."""
    test_dir = project_root / "tests" / "fixtures"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


@pytest.fixture(scope="function", autouse=True)
def setup_test_environment(project_root: Path):
    """
    Set up test environment before each test.
    
    This fixture automatically runs before each test to ensure
    the project root is in the Python path.
    """
    import sys
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    yield
    # Cleanup if needed
    pass


