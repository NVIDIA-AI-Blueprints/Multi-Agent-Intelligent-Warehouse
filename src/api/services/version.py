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

The version identifies the build; no release number is written in the code.
It is resolved, in order, from:

1. ``MAIW_APP_VERSION``: an explicit version, reported as given.
2. ``git describe`` of this checkout (running from source):
   on a release tag ``v2.1.1``                -> ``2.1.1`` (build ``release``)
   43 commits after it                        -> ``2.1.1+43.g18f2d6d0b1ae``
   with uncommitted changes                   -> ``...+...dirty``
   no release tag in the history (shallow)    -> ``0.0.0+g18f2d6d0b1ae``
   (everything but an exact, clean tag is build ``development``; ``+`` is
   SemVer build metadata, so the number is never a guess at the next release)
3. ``MAIW_BUILD_DESCRIBE``: the same ``git describe`` output, baked into a
   container image at build time (images have no ``.git``).
4. ``VERSION``, the older image build argument, unless it is a placeholder
   (``0.0.0``, ``latest``, ``unknown``), reported as build ``declared``.
5. ``0.0.0+unknown`` (build ``unknown``).

The commit is ``git rev-parse HEAD``, else ``GIT_SHA`` from the image build.
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Mapping, Optional
import logging

logger = logging.getLogger(__name__)

# The checkout this module belongs to; git runs here, not in the caller's cwd.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLACEHOLDERS = {"", "unknown", "latest", "none", "0.0.0", "0.0.0-dev"}
_DESCRIBE_ARGS = ["describe", "--tags", "--match", "v[0-9]*", "--long", "--dirty", "--abbrev=12"]
_TAG_DESCRIBE = re.compile(
    r"^v?(?P<base>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)"
    r"-(?P<distance>\d+)-g(?P<sha>[0-9a-f]{7,40})(?P<dirty>-dirty)?$"
)
_BARE_DESCRIBE = re.compile(r"^(?P<sha>[0-9a-f]{7,40})(?P<dirty>-dirty)?$")


@dataclass(frozen=True)
class BuildIdentity:
    """What this build is: version, kind of build, commit, and where it came from."""

    version: str
    build: str  # release | development | declared | unknown
    commit: str  # full SHA when known, else an abbreviated one, else "unknown"
    source: str  # MAIW_APP_VERSION | git | MAIW_BUILD_DESCRIBE | VERSION | none


def version_from_describe(describe: str) -> Optional[tuple]:
    """Turn ``git describe --long --dirty`` output into (version, build, sha)."""
    describe = (describe or "").strip()
    match = _TAG_DESCRIBE.match(describe)
    if match:
        distance = int(match["distance"])
        dirty = bool(match["dirty"])
        if distance == 0 and not dirty:
            return match["base"], "release", match["sha"]
        meta = [str(distance), f"g{match['sha']}"] if distance else []
        if dirty:
            meta.append("dirty")
        return f"{match['base']}+{'.'.join(meta)}", "development", match["sha"]
    match = _BARE_DESCRIBE.match(describe)
    if match:
        meta = f"g{match['sha']}" + (".dirty" if match["dirty"] else "")
        return f"0.0.0+{meta}", "development", match["sha"]
    return None


def _git(*args: str) -> Optional[str]:
    """Run git in this checkout; None when there is no checkout or git fails."""
    if not (_REPO_ROOT / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            cwd=_REPO_ROOT,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    return result.stdout.strip() or None


def _env(env: Mapping[str, str], key: str) -> Optional[str]:
    value = (env.get(key) or "").strip()
    return None if value.lower() in _PLACEHOLDERS else value


def resolve_build_identity(env: Optional[Mapping[str, str]] = None) -> BuildIdentity:
    """Resolve the build identity (see the module docstring for the order)."""
    env = os.environ if env is None else env
    commit = _git("rev-parse", "HEAD") or _env(env, "GIT_SHA") or "unknown"

    explicit = (env.get("MAIW_APP_VERSION") or "").strip()
    if explicit:
        return BuildIdentity(explicit, "declared", commit, "MAIW_APP_VERSION")

    candidates = [
        ("git", _git(*_DESCRIBE_ARGS) or _git("describe", "--always", "--dirty", "--abbrev=12")),
        ("MAIW_BUILD_DESCRIBE", _env(env, "MAIW_BUILD_DESCRIBE")),
    ]
    for source, describe in candidates:
        parsed = version_from_describe(describe) if describe else None
        if parsed:
            version, build, sha = parsed
            if commit == "unknown":
                commit = sha
            return BuildIdentity(version, build, commit, source)

    declared = _env(env, "VERSION")
    if declared:
        return BuildIdentity(declared.lstrip("v"), "declared", commit, "VERSION")
    return BuildIdentity("0.0.0+unknown", "unknown", commit, "none")


class VersionService:
    """
    Service for managing and providing version information.

    This service extracts version information from git, environment variables,
    and build metadata to provide comprehensive version tracking.
    """

    def __init__(self):
        """Initialize the version service."""
        self.identity = resolve_build_identity()
        self.version = self.identity.version
        self.commit = self.identity.commit
        self.git_sha = self.commit[:8]
        env_build_time = os.getenv("BUILD_TIME", "").strip()
        self.build_time = (
            env_build_time
            if env_build_time and env_build_time != "unknown"
            else datetime.utcnow().isoformat()
        )
        self.build_info = self._get_build_info()

    def _get_commit_count(self) -> int:
        """
        Get total commit count.

        Returns:
            int: Number of commits
        """
        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
                cwd=_REPO_ROOT,
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
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
                cwd=_REPO_ROOT,
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
            "build": self.identity.build,
            "version_source": self.identity.source,
            "commit": self.commit,
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
            "build": self.identity.build,
            "commit": self.commit,
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
        return re.split(r"[-+]", self.version)[0]  # Drop pre-release and build metadata


# Global instance
version_service = VersionService()
