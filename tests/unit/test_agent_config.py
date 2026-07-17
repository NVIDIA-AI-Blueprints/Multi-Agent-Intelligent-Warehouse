"""Tests for loading agent configuration files."""

from pathlib import Path

import pytest

from src.api.services.agent_config import AgentConfigLoader


def test_default_config_directory_loads_agent() -> None:
    """Load an agent from the repository-relative default directory."""
    config = AgentConfigLoader().load_agent_config("safety")

    assert config.name == "Safety & Compliance Agent"


def test_missing_config_directory_fails_fast(tmp_path: Path) -> None:
    """Reject a runtime image that omits agent configuration files."""
    missing_config_dir = tmp_path / "agents"

    with pytest.raises(FileNotFoundError, match="Agent config directory does not exist"):
        AgentConfigLoader(missing_config_dir)
