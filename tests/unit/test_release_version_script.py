# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
scripts/security/release_version.sh: the version a build is stamped with (#268).

CI stamped every SBOM with the latest tag reachable from the commit, so the
v2.1.1 candidate's SBOMs said 2.1.0 and every later main build said 2.1.1.
The helper now returns the tag only for a tagged commit, the version being
prepared when MAIW_RELEASE_VERSION is set, and otherwise a development
version that cannot be mistaken for a release. Each test runs the real script
in a throwaway git repository.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "security" / "release_version.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="bash script under test"
)


def _semver():
    spec = importlib.util.spec_from_file_location(
        "validate_sbom", REPO / "scripts" / "security" / "validate_sbom.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SEMVER


SEMVER = _semver()


class Repo:
    def __init__(self, path: Path):
        self.path = path
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        self.commits = 0

    def git(self, *args: str) -> str:
        return subprocess.run(
            [
                "git",
                "-C",
                str(self.path),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.com",
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self) -> str:
        self.commits += 1
        (self.path / "f.txt").write_text(str(self.commits))
        self.git("add", "f.txt")
        self.git("commit", "-qm", f"c{self.commits}")
        return self.git("rev-parse", "--short=7", "HEAD")

    def tag(self, name: str, annotated: bool = True) -> None:
        if annotated:
            self.git("tag", "-a", name, "-m", name)
        else:
            self.git("tag", name)

    def version(
        self, *args: str, release: str | None = None
    ) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "MAIW_RELEASE_VERSION"}
        if release is not None:
            env["MAIW_RELEASE_VERSION"] = release
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=self.path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )


@pytest.fixture()
def repo(tmp_path):
    return Repo(tmp_path / "r")


def _ok(proc: subprocess.CompletedProcess) -> str:
    assert proc.returncode == 0, proc.stderr
    version = proc.stdout.strip()
    assert SEMVER.match(version), version  # validate_sbom.py accepts it
    return version


def test_tagged_commit_is_its_release(repo):
    repo.commit()
    repo.tag("v2.1.0")
    repo.commit()
    repo.tag("v2.1.1")
    assert _ok(repo.version()) == "2.1.1"


def test_lightweight_tag_counts_too(repo):
    repo.commit()
    repo.tag("v2.1.1", annotated=False)
    assert _ok(repo.version()) == "2.1.1"


def test_commit_after_a_tag_is_a_development_version_not_the_release(repo):
    # The #268 bug: main after v2.1.1 was stamped 2.1.1.
    repo.commit()
    repo.tag("v2.1.1")
    repo.commit()
    sha = repo.commit()
    version = _ok(repo.version())
    assert version == f"2.1.1+2.g{sha}"
    assert version != "2.1.1"


def test_release_candidate_override_is_used_before_the_tag_exists(repo):
    # The #268 bug: the v2.1.1 candidate was stamped 2.1.0.
    repo.commit()
    repo.tag("v2.1.0")
    repo.commit()
    assert _ok(repo.version(release="2.1.1")) == "2.1.1"
    assert _ok(repo.version(release="v2.1.1")) == "2.1.1"
    assert _ok(repo.version(release="2.2.0-rc.1")) == "2.2.0-rc.1"


def test_empty_override_is_ignored(repo):
    repo.commit()
    repo.tag("v2.1.0")
    assert _ok(repo.version(release="")) == "2.1.0"


def test_override_matching_the_tag_is_accepted(repo):
    repo.commit()
    repo.tag("v2.1.1")
    assert _ok(repo.version(release="2.1.1")) == "2.1.1"


@pytest.mark.parametrize("bad", ["2.1", "2.1.1+16.gabc", "latest", "2.1.1 ", "x2.1.1"])
def test_malformed_override_fails(repo, bad):
    repo.commit()
    proc = repo.version(release=bad)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "not a release version" in proc.stderr


def test_override_contradicting_the_tag_fails(repo):
    repo.commit()
    repo.tag("v2.1.1")
    proc = repo.version(release="2.1.2")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "contradicts tag v2.1.1" in proc.stderr


def test_no_tag_reachable_is_0_0_0_with_the_sha(repo):
    sha = repo.commit()
    assert _ok(repo.version()) == f"0.0.0+g{sha}"


def test_non_release_tags_are_ignored(repo):
    repo.commit()
    repo.tag("v2.1.0")
    repo.commit()
    repo.tag("phase-14-baseline")
    sha = repo.git("rev-parse", "--short=7", "HEAD")
    assert _ok(repo.version()) == f"2.1.0+1.g{sha}"


def test_development_version_after_a_pre_release_tag(repo):
    repo.commit()
    repo.tag("v2.2.0-rc.1")
    sha = repo.commit()
    assert _ok(repo.version()) == f"2.2.0-rc.1+1.g{sha}"


def test_explicit_revision(repo):
    repo.commit()
    repo.tag("v2.1.0")
    first = repo.git("rev-parse", "HEAD")
    repo.commit()
    assert _ok(repo.version(first)) == "2.1.0"
    assert _ok(repo.version("v2.1.0")) == "2.1.0"
