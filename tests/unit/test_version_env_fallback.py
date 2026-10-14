"""Version info must use the build-time env when git is unavailable (container images)."""

import subprocess

import pytest

from src.api.services import version as version_module


def _no_git(*args, **kwargs):
    raise FileNotFoundError("git")


@pytest.fixture
def no_git(monkeypatch):
    monkeypatch.setattr(version_module.subprocess, "run", _no_git)


def test_git_sha_falls_back_to_env(monkeypatch, no_git):
    monkeypatch.setenv("GIT_SHA", "7bfc2c59929b784c")
    monkeypatch.setenv("BUILD_TIME", "2026-10-14T18:00:00Z")
    svc = version_module.VersionService()
    assert svc.git_sha == "7bfc2c59"
    assert svc.build_time == "2026-10-14T18:00:00Z"


@pytest.mark.parametrize("value", ["", "unknown", "   "])
def test_git_sha_unknown_when_env_unset_or_placeholder(monkeypatch, no_git, value):
    monkeypatch.setenv("GIT_SHA", value)
    monkeypatch.setenv("BUILD_TIME", "unknown")
    svc = version_module.VersionService()
    assert svc.git_sha == "unknown"
    assert svc.build_time != "unknown"


def test_git_still_preferred_when_available(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "deadbeefcafe")

    def fake_run(cmd, **kwargs):
        out = "abcdef1234567890\n" if cmd[:2] == ["git", "rev-parse"] else "v2.0.1\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(version_module.subprocess, "run", fake_run)
    svc = version_module.VersionService()
    assert svc.git_sha == "abcdef12"
