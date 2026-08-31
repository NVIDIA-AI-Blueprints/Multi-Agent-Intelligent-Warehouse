# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for python -m maiw_world CLI commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable


def run_cli(*args, cwd=None):
    result = subprocess.run(
        [PYTHON, "-m", "maiw_world", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


# ── generate ──────────────────────────────────────────────────────────────────


def test_generate_creates_datapack(tmp_path):
    r = run_cli("generate", "--output", str(tmp_path / "pack"), cwd=str(tmp_path))
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert (tmp_path / "pack" / "manifest.json").exists()


def test_generate_with_yaml_config(tmp_path):
    import yaml

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "warehouse_id": "TEST",
                "dataset_id": "test-v1",
                "seed": 1,
                "facility": {
                    "zone_count": 1,
                    "location_count": 2,
                    "dock_door_count": 1,
                },
                "inventory": {"sku_count": 5, "low_stock_pct": 0.0},
                "labor": {"workers_per_shift": 2, "shift_count": 1},
                "equipment": {"agv_count": 1},
                "orders": {"daily_order_count": 2, "lines_per_order_mean": 1.0},
                "waves": {"active_wave_count": 1, "task_count": 2},
            }
        )
    )
    r = run_cli(
        "generate",
        "--config", str(cfg_path),
        "--output", str(tmp_path / "pack"),
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    manifest = json.loads((tmp_path / "pack" / "manifest.json").read_text())
    assert manifest["warehouse_id"] == "TEST"


def test_generate_no_overwrite_existing(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    r = run_cli("generate", "--output", str(pack))
    # Should warn and skip without error
    combined = r.stdout.lower() + r.stderr.lower()
    assert "exists" in combined or r.returncode == 0, (
        f"Expected 'exists' warning or returncode=0; got returncode={r.returncode}"
    )


def test_generate_overwrite_flag(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    r = run_cli("generate", "--output", str(pack), "--overwrite")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert (pack / "manifest.json").exists()


# ── validate ──────────────────────────────────────────────────────────────────


def test_validate_clean_pack(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    r = run_cli("validate", str(pack))
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "PASS" in r.stdout


def test_validate_missing_pack_fails(tmp_path):
    r = run_cli("validate", str(tmp_path / "nonexistent"))
    assert r.returncode != 0


def test_validate_tampered_pack_fails(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    # Tamper with entities file
    p = pack / "graph" / "entities.jsonl"
    p.write_text(p.read_text() + '\n{"id":"bad-injection"}\n')
    r = run_cli("validate", str(pack))
    assert r.returncode != 0


# ── inspect ───────────────────────────────────────────────────────────────────


def test_inspect_summary(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    r = run_cli("inspect", str(pack), "--summary")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    combined = r.stdout.lower()
    assert "warehouse" in combined or "entities" in combined


def test_inspect_entity(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    # The default preset creates DC-47 warehouse entity with id=warehouse_id
    manifest = json.loads((pack / "manifest.json").read_text())
    wh_id = manifest["warehouse_id"]
    r = run_cli("inspect", str(pack), "--entity", wh_id)
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert wh_id in r.stdout


def test_inspect_nonexistent_entity(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    r = run_cli("inspect", str(pack), "--entity", "nonexistent-xyz-9999")
    assert r.returncode != 0


# ── scenarios ─────────────────────────────────────────────────────────────────


def test_scenarios_lists_all(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    r = run_cli("scenarios", str(pack))
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    # Check key scenarios appear
    assert "labor_constraint" in r.stdout or "labor" in r.stdout.lower()


# ── checksum ──────────────────────────────────────────────────────────────────


def test_checksum_output(tmp_path):
    pack = tmp_path / "pack"
    run_cli("generate", "--output", str(pack))
    r = run_cli("checksum", str(pack))
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    # Output should contain a hex checksum (64 chars)
    import re
    assert re.search(r"[0-9a-f]{16,}", r.stdout), "No checksum found in output"


# ── config.from_yaml ──────────────────────────────────────────────────────────


def test_from_yaml_roundtrip(tmp_path):
    import yaml
    from maiw_world.config import WarehouseWorldConfig

    cfg = WarehouseWorldConfig.dc47_demo()
    yml_path = tmp_path / "config.yaml"
    with open(yml_path, "w") as f:
        yaml.dump(cfg.model_dump(), f)

    cfg2 = WarehouseWorldConfig.from_yaml(yml_path)
    assert cfg2.warehouse_id == cfg.warehouse_id
    assert cfg2.seed == cfg.seed
    assert cfg2.dataset_id == cfg.dataset_id
    assert cfg2.facility.zone_count == cfg.facility.zone_count
    assert cfg2.inventory.sku_count == cfg.inventory.sku_count


def test_from_yaml_small_config():
    """The canonical small.yaml round-trips through from_yaml."""
    from maiw_world.config import WarehouseWorldConfig

    yaml_path = Path(__file__).parents[3] / "data" / "world-configs" / "small.yaml"
    if not yaml_path.exists():
        pytest.skip("small.yaml not found in repo — skipping")

    cfg = WarehouseWorldConfig.from_yaml(yaml_path)
    assert cfg.warehouse_id == "DC-SMALL"
    assert cfg.seed == 42
    assert cfg.inventory.sku_count == 100


def test_from_yaml_dc47_config():
    """The canonical dc47-demo.yaml round-trips through from_yaml."""
    from maiw_world.config import WarehouseWorldConfig

    yaml_path = Path(__file__).parents[3] / "data" / "world-configs" / "dc47-demo.yaml"
    if not yaml_path.exists():
        pytest.skip("dc47-demo.yaml not found in repo — skipping")

    cfg = WarehouseWorldConfig.from_yaml(yaml_path)
    assert cfg.warehouse_id == "DC-47"
    assert cfg.dataset_id == "dc47-demo-v1"
    assert cfg.seed == 42
    assert cfg.inventory.sku_count == 25000
