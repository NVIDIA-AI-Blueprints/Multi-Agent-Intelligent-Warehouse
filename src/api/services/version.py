# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Version Service for Warehouse Operational Assistant

This service provides comprehensive version information including:
- Git version and commit SHA
- Build timestamp and metadata
- Environment information
- Docker image details
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class VersionService:
    """
    Service for managing and providing version information.

    This service extracts version information from git, environment variables,
    and build metadata to provide comprehensive version tracking.
    """

    def __init__(self):
        """Initialize the version service."""
        self.version = self._get_version()
        self.git_sha = self._get_git_sha()
        self.build_time = os.getenv("BUILD_TIME") or datetime.utcnow().isoformat()
        self.build_info = self._get_build_info()

    @staticmethod
    def _env_value(name: str) -> Optional[str]:
        """Return a meaningful environment value, ignoring empty/unknown defaults."""
        value = os.getenv(name)
        if value and value.strip() and value.strip().lower() != "unknown":
            return value.strip()
        return None

    @staticmethod
    def _has_git_metadata() -> bool:
        """Check whether git metadata exists before invoking git commands."""
        if os.getenv("GIT_DIR"):
            return True

        current = Path.cwd()
        for path in (current, *current.parents):
            if (path / ".git").exists():
                return True
        return False

    def _get_version(self) -> str:
        """
        Get version from git tag or fallback to environment variable.

        Returns:
            str: Version string (e.g., "1.0.0", "1.0.0-dev")
        """
        env_version = self._env_value("VERSION")
        if env_version:
            logger.info(f"Build version: {env_version}")
            return env_version

        if not self._has_git_metadata():
            logger.info("Git metadata unavailable; using default version")
            return "0.0.0-dev"

        try:
            # Try to get version from git tag
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            version = result.stdout.strip()
            logger.info(f"Git version: {version}")
            return version
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
        ) as e:
            logger.warning(f"Could not get git version: {e}")
            # Fallback to environment variable or default
            return os.getenv("VERSION", "0.0.0-dev")

    def _get_git_sha(self) -> str:
        """
        Get current git commit SHA.

        Returns:
            str: Short git SHA (8 characters)
        """
        env_sha = self._env_value("GIT_SHA")
        if env_sha:
            sha = env_sha[:8]
            logger.info(f"Build Git SHA: {sha}")
            return sha

        if not self._has_git_metadata():
            logger.info("Git metadata unavailable; using unknown Git SHA")
            return "unknown"

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            sha = result.stdout.strip()[:8]
            logger.info(f"Git SHA: {sha}")
            return sha
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
        ) as e:
            logger.warning(f"Could not get git SHA: {e}")
            return "unknown"

    def _get_commit_count(self) -> int:
        """
        Get total commit count.

        Returns:
            int: Number of commits
        """
        if not self._has_git_metadata():
            logger.info("Git metadata unavailable; using commit count 0")
            return 0

        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            count = int(result.stdout.strip())
            logger.info(f"Commit count: {count}")
            return count
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
            ValueError,
        ) as e:
            logger.warning(f"Could not get commit count: {e}")
            return 0

    def _get_branch_name(self) -> str:
        """
        Get current git branch name.

        Returns:
            str: Branch name
        """
        env_branch = self._env_value("GIT_BRANCH")
        if env_branch:
            logger.info(f"Build Git branch: {env_branch}")
            return env_branch

        if not self._has_git_metadata():
            logger.info("Git metadata unavailable; using unknown Git branch")
            return "unknown"

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            branch = result.stdout.strip()
            logger.info(f"Git branch: {branch}")
            return branch
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
        ) as e:
            logger.warning(f"Could not get git branch: {e}")
            return "unknown"

    def _get_build_info(self) -> Dict[str, Any]:
        """
        Get comprehensive build information.

        Returns:
            Dict[str, Any]: Complete build information
        """
        return {
            "version": self.version,
            "git_sha": self.git_sha,
            "git_branch": self._get_branch_name(),
            "build_time": self.build_time,
            "commit_count": self._get_commit_count(),
            "python_version": sys.version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "docker_image": os.getenv("DOCKER_IMAGE", "unknown"),
            "build_host": os.getenv("HOSTNAME", "unknown"),
            "build_user": os.getenv("USER", "unknown"),
        }

    def get_version_info(self) -> Dict[str, Any]:
        """
        Get complete version information for API responses.

        Returns:
            Dict[str, Any]: Version information
        """
        return {
            "version": self.version,
            "git_sha": self.git_sha,
            "build_time": self.build_time,
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

    def get_detailed_info(self) -> Dict[str, Any]:
        """
        Get detailed build information for debugging.

        Returns:
            Dict[str, Any]: Detailed build information
        """
        return self.build_info

    def is_development(self) -> bool:
        """
        Check if running in development environment.

        Returns:
            bool: True if development environment
        """
        return os.getenv("ENVIRONMENT", "development").lower() in ["development", "dev"]

    def is_production(self) -> bool:
        """
        Check if running in production environment.

        Returns:
            bool: True if production environment
        """
        return os.getenv("ENVIRONMENT", "development").lower() in ["production", "prod"]

    def get_version_display(self) -> str:
        """
        Get formatted version string for display.

        Returns:
            str: Formatted version string
        """
        return f"{self.version} ({self.git_sha})"

    def get_short_version(self) -> str:
        """
        Get short version string.

        Returns:
            str: Short version string
        """
        return self.version.split("-")[0]  # Remove pre-release info


# Global instance
version_service = VersionService()
