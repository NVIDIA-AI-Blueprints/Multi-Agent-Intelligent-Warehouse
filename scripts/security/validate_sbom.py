#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Stamp a CycloneDX SBOM with MAIW release identity and validate it.

    python scripts/security/validate_sbom.py SBOM.json \\
        --artifact maiw-backend --git-sha <sha> --version 2.1.0 \\
        [--artifact-digest sha256:...] [--min-components 50]

Adds metadata properties (``maiw:artifact``, ``maiw:git_sha``,
``maiw:release_version``, ``maiw:artifact_digest``, ``maiw:repository``),
then fails unless the document:
- validates against the CycloneDX JSON schema of its declared specVersion
  (cyclonedx-python-lib's strict validator), and
- lists at least ``--min-components`` components, so an empty or truncated
  inventory never passes, and records the generating tool.

Prints a one-line summary. Exit 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY = "https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse"


def stamp(bom: dict, *, artifact: str, git_sha: str, version: str, digest: str | None) -> dict:
    metadata = bom.setdefault("metadata", {})
    properties = [p for p in metadata.get("properties", []) if not p.get("name", "").startswith("maiw:")]
    identity = {
        "maiw:artifact": artifact,
        "maiw:git_sha": git_sha,
        "maiw:release_version": version,
        "maiw:repository": REPOSITORY,
    }
    if digest:
        identity["maiw:artifact_digest"] = digest
    properties.extend({"name": k, "value": v} for k, v in identity.items())
    metadata["properties"] = properties
    return bom


def tool_names(bom: dict) -> list[str]:
    tools = bom.get("metadata", {}).get("tools", [])
    if isinstance(tools, dict):  # CycloneDX >= 1.5: {"components": [...]}
        tools = tools.get("components", []) + tools.get("services", [])
    return [f"{t.get('name')} {t.get('version', '')}".strip() for t in tools]


def validate(bom: dict, raw: str, min_components: int) -> list[str]:
    from cyclonedx.schema import SchemaVersion
    from cyclonedx.validation.json import JsonStrictValidator

    errors = []
    if bom.get("bomFormat") != "CycloneDX":
        errors.append(f"bomFormat is {bom.get('bomFormat')!r}, expected 'CycloneDX'")
        return errors
    spec = bom.get("specVersion", "")
    try:
        schema = SchemaVersion.from_version(spec)
    except Exception:
        errors.append(f"unsupported specVersion {spec!r}")
        return errors
    error = JsonStrictValidator(schema).validate_str(raw)
    if error is not None:
        errors.append(f"schema {spec}: {error}")
    count = len(bom.get("components", []))
    if count < min_components:
        errors.append(f"{count} components, expected at least {min_components}")
    if not tool_names(bom):
        errors.append("metadata.tools is empty (generation tool not recorded)")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sbom", type=Path)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifact-digest")
    parser.add_argument("--min-components", type=int, default=1)
    args = parser.parse_args(argv)

    bom = json.loads(args.sbom.read_text())
    bom = stamp(
        bom,
        artifact=args.artifact,
        git_sha=args.git_sha,
        version=args.version,
        digest=args.artifact_digest,
    )
    raw = json.dumps(bom, indent=2)
    args.sbom.write_text(raw + "\n")

    errors = validate(bom, raw, args.min_components)
    summary = (
        f"{args.sbom.name}: CycloneDX {bom.get('specVersion')}, "
        f"{len(bom.get('components', []))} components, "
        f"tools={tool_names(bom)}, git_sha={args.git_sha[:12]}"
    )
    if errors:
        for error in errors:
            print(f"::error title=Invalid SBOM {args.sbom.name}::{error}")
        print(f"INVALID {summary}")
        return 1
    print(f"VALID {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
