# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The reported version identifies the build, from git or from the image build.

The git cases run real ``git`` in a temporary repository, so they test the
same ``git describe`` the API runs from a source checkout.
"""

from __future__ import annotations

import subprocess

import pytest

from src.api.services import version as version_module
from src.api.services.version import resolve_build_identity, version_from_describe

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
GIT += ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]
IMAGE_SHA = "6d1395b0c0ffee00000000000000000000000001"


def _git(repo, *args):
    out = subprocess.run(
        [*GIT, *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _commit(repo, name):
    (repo / name).write_text(name)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    monkeypatch.setattr(version_module, "_REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def image(tmp_path, monkeypatch):
    """A container image: no .git next to the code."""
    monkeypatch.setattr(version_module, "_REPO_ROOT", tmp_path)
    return tmp_path


def test_tagged_build_reports_the_release(repo):
    sha = _commit(repo, "a")
    _git(repo, "tag", "v9.8.7")
    assert resolve_build_identity({}) == version_module.BuildIdentity(
        "9.8.7", "release", sha, "git"
    )


def test_development_build_counts_commits_after_the_release(repo):
    _commit(repo, "a")
    _git(repo, "tag", "v9.8.7")
    _commit(repo, "b")
    sha = _commit(repo, "c")
    identity = resolve_build_identity({})
    # Build metadata, not a guess at the next release number.
    assert identity.version == f"9.8.7+2.g{sha[:12]}"
    assert (identity.build, identity.commit, identity.source) == (
        "development",
        sha,
        "git",
    )


def test_uncommitted_changes_are_reported(repo):
    _commit(repo, "a")
    _git(repo, "tag", "v9.8.7")
    (repo / "a").write_text("changed")
    identity = resolve_build_identity({})
    assert (identity.version, identity.build) == ("9.8.7+dirty", "development")


def test_only_release_tags_count(repo):
    _commit(repo, "a")
    _git(repo, "tag", "v9.8.7")
    sha = _commit(repo, "b")
    _git(repo, "tag", "phase-14-baseline")
    assert resolve_build_identity({}).version == f"9.8.7+1.g{sha[:12]}"


def test_history_without_a_release_tag_still_names_the_commit(repo):
    # e.g. a shallow CI checkout
    sha = _commit(repo, "a")
    identity = resolve_build_identity({})
    assert (identity.version, identity.build, identity.commit) == (
        f"0.0.0+g{sha[:12]}",
        "development",
        sha,
    )


def test_git_wins_over_the_image_build_environment(repo):
    sha = _commit(repo, "a")
    _git(repo, "tag", "v9.8.7")
    env = {"MAIW_BUILD_DESCRIBE": "v1.0.0-5-g0123456789ab", "GIT_SHA": IMAGE_SHA}
    assert resolve_build_identity(env) == version_module.BuildIdentity(
        "9.8.7", "release", sha, "git"
    )


@pytest.mark.parametrize(
    ("describe", "version", "build"),
    [
        ("v2.1.1-0-g6d1395b0c0ff", "2.1.1", "release"),
        ("v2.1.1-43-g18f2d6d0b1ae", "2.1.1+43.g18f2d6d0b1ae", "development"),
        (
            "v2.1.1-43-g18f2d6d0b1ae-dirty",
            "2.1.1+43.g18f2d6d0b1ae.dirty",
            "development",
        ),
    ],
)
def test_image_reports_the_build_it_was_made_from(image, describe, version, build):
    identity = resolve_build_identity(
        {"MAIW_BUILD_DESCRIBE": describe, "GIT_SHA": IMAGE_SHA}
    )
    assert identity == version_module.BuildIdentity(
        version, build, IMAGE_SHA, "MAIW_BUILD_DESCRIBE"
    )


def test_image_without_a_commit_takes_it_from_describe(image):
    identity = resolve_build_identity({"MAIW_BUILD_DESCRIBE": "v2.1.1-3-g18f2d6d0b1ae"})
    assert identity.commit == "18f2d6d0b1ae"


@pytest.mark.parametrize("placeholder", ["", "0.0.0", "latest", "unknown"])
def test_placeholders_are_not_reported_as_a_version(image, placeholder):
    env = {"VERSION": placeholder, "GIT_SHA": "unknown", "MAIW_BUILD_DESCRIBE": ""}
    assert resolve_build_identity(env) == version_module.BuildIdentity(
        "0.0.0+unknown", "unknown", "unknown", "none"
    )


def test_a_declared_image_version_is_marked_declared(image):
    identity = resolve_build_identity({"VERSION": "v2.1.1", "GIT_SHA": IMAGE_SHA})
    assert identity == version_module.BuildIdentity(
        "2.1.1", "declared", IMAGE_SHA, "VERSION"
    )


def test_explicit_version_wins_and_keeps_the_commit(repo):
    sha = _commit(repo, "a")
    identity = resolve_build_identity({"MAIW_APP_VERSION": "2.2.0-rc.1"})
    assert identity == version_module.BuildIdentity(
        "2.2.0-rc.1", "declared", sha, "MAIW_APP_VERSION"
    )


@pytest.mark.parametrize(
    ("describe", "expected"),
    [
        ("v2.2.0-rc.1-3-gabcdef123456", ("2.2.0-rc.1+3.gabcdef123456", "development")),
        ("abcdef123456", ("0.0.0+gabcdef123456", "development")),
        ("abcdef123456-dirty", ("0.0.0+gabcdef123456.dirty", "development")),
        ("not a describe", None),
        ("", None),
    ],
)
def test_describe_parsing(describe, expected):
    parsed = version_from_describe(describe)
    assert (parsed[:2] if parsed else None) == expected


def test_version_service_reports_build_and_full_commit(image, monkeypatch):
    monkeypatch.delenv("MAIW_APP_VERSION", raising=False)
    monkeypatch.setenv("MAIW_BUILD_DESCRIBE", "v2.1.1-43-g18f2d6d0b1ae")
    monkeypatch.setenv("GIT_SHA", IMAGE_SHA)
    info = version_module.VersionService().get_version_info()
    assert info["version"] == "2.1.1+43.g18f2d6d0b1ae"
    assert info["build"] == "development"
    assert info["commit"] == IMAGE_SHA
    assert info["git_sha"] == IMAGE_SHA[:8]
