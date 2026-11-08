# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""scripts/security/validate_sbom.py: release identity stamping and validation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("cyclonedx.validation.json")

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/security/validate_sbom.py"
SHA = "0" * 40


def _load():
    spec = importlib.util.spec_from_file_location("validate_sbom", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_sbom = _load()


def _bom(components: int = 3, tools: bool = True) -> dict:
    bom = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"timestamp": "2026-11-02T00:00:00Z"},
        "components": [
            {
                "bom-ref": f"pkg:pypi/pkg{i}@1.0.{i}",
                "type": "library",
                "name": f"pkg{i}",
                "version": f"1.0.{i}",
                "purl": f"pkg:pypi/pkg{i}@1.0.{i}",
            }
            for i in range(components)
        ],
    }
    if tools:
        bom["metadata"]["tools"] = {
            "components": [
                {"type": "application", "name": "trivy", "version": "0.70.0"}
            ]
        }
    return bom


def _run(tmp_path, bom, *extra):
    path = tmp_path / "sbom.cdx.json"
    path.write_text(json.dumps(bom))
    code = validate_sbom.main(
        [
            str(path),
            "--artifact",
            "maiw-backend",
            "--git-sha",
            SHA,
            "--version",
            "2.1.0",
            *extra,
        ]
    )
    return code, json.loads(path.read_text())


def test_valid_sbom_is_stamped_with_release_identity(tmp_path, capsys):
    code, bom = _run(
        tmp_path, _bom(), "--artifact-digest", "sha256:abc", "--min-components", "3"
    )
    assert code == 0
    props = {p["name"]: p["value"] for p in bom["metadata"]["properties"]}
    assert props == {
        "maiw:artifact": "maiw-backend",
        "maiw:git_sha": SHA,
        "maiw:release_version": "2.1.0",
        "maiw:repository": validate_sbom.REPOSITORY,
        "maiw:artifact_digest": "sha256:abc",
    }
    assert capsys.readouterr().out.startswith(
        "VALID sbom.cdx.json: CycloneDX 1.6, 3 components"
    )


def test_truncated_inventory_fails(tmp_path, capsys):
    code, _ = _run(tmp_path, _bom(components=2), "--min-components", "50")
    assert code == 1
    assert "2 components, expected at least 50" in capsys.readouterr().out


def test_missing_generation_tool_fails(tmp_path, capsys):
    code, _ = _run(tmp_path, _bom(tools=False))
    assert code == 1
    assert "generation tool not recorded" in capsys.readouterr().out


def test_schema_violation_fails(tmp_path, capsys):
    bom = _bom()
    bom["components"][0]["type"] = "not-a-component-type"
    code, _ = _run(tmp_path, bom)
    assert code == 1
    assert "schema 1.6" in capsys.readouterr().out


def test_restamping_replaces_previous_identity(tmp_path):
    bom = _bom()
    bom["metadata"]["properties"] = [
        {"name": "maiw:git_sha", "value": "stale"},
        {"name": "aquasecurity:trivy:SchemaVersion", "value": "2"},
    ]
    _, stamped = _run(tmp_path, bom)
    names = [p["name"] for p in stamped["metadata"]["properties"]]
    assert names.count("maiw:git_sha") == 1
    assert "aquasecurity:trivy:SchemaVersion" in names


@pytest.mark.parametrize(
    "version", ["2.1.1", "2.2.0-rc.1", "2.1.1+16.g4d2e0c4", "0.0.0+g4d2e0c4"]
)
def test_release_and_development_versions_are_accepted(tmp_path, version):
    path = tmp_path / "sbom.cdx.json"
    path.write_text(json.dumps(_bom()))
    code = validate_sbom.main(
        [
            str(path),
            "--artifact",
            "maiw-backend",
            "--git-sha",
            SHA,
            "--version",
            version,
        ]
    )
    assert code == 0
    props = {
        p["name"]: p["value"]
        for p in json.loads(path.read_text())["metadata"]["properties"]
    }
    assert props["maiw:release_version"] == version


@pytest.mark.parametrize(
    "version", ["v2.1.1", "2.1", "", "2.1.1+", "02.1.1", "unknown"]
)
def test_non_semantic_version_fails(tmp_path, capsys, version):
    path = tmp_path / "sbom.cdx.json"
    path.write_text(json.dumps(_bom()))
    code = validate_sbom.main(
        [
            str(path),
            "--artifact",
            "maiw-backend",
            "--git-sha",
            SHA,
            "--version",
            version,
        ]
    )
    assert code == 1
    assert "is not a semantic version" in capsys.readouterr().out
