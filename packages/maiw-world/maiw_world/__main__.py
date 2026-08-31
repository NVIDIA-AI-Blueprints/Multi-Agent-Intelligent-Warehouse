# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Warehouse World CLI.

Usage:
    python -m maiw_world generate  [--config <yaml>] [--output <dir>] [--overwrite]
    python -m maiw_world validate  <pack_dir>
    python -m maiw_world inspect   <pack_dir> [--summary] [--entity <id>]
    python -m maiw_world scenarios <pack_dir>
    python -m maiw_world checksum  <pack_dir>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _header(title: str) -> None:
    print(f"\n{title}\n")


def _row(label: str, value: str, width: int = 16) -> None:
    print(f"  {label:<{width}} {value}")


def _separator() -> None:
    print()


# ── generate ──────────────────────────────────────────────────────────────────

def cmd_generate(args: argparse.Namespace) -> int:
    from maiw_world.config import WarehouseWorldConfig
    from maiw_world.generator import WarehouseWorldGenerator
    from maiw_world.datapack import WarehouseDataPack, compute_semantic_checksum

    _header("MAIW Warehouse World Generator")

    # Load config
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
            return 1
        _row("Config", str(config_path))
        try:
            config = WarehouseWorldConfig.from_yaml(config_path)
        except Exception as exc:
            print(f"ERROR: Failed to load config: {exc}", file=sys.stderr)
            return 1
    else:
        _row("Config", "(default: dc47_demo preset)")
        config = WarehouseWorldConfig.dc47_demo()

    output_dir = Path(args.output) if args.output else Path(f"data/worlds/{config.dataset_id}")
    _row("Output", str(output_dir))
    _separator()

    # Check for existing pack
    if output_dir.exists() and (output_dir / "manifest.json").exists():
        if not args.overwrite:
            print(f"  WARNING: DataPack already exists at: {output_dir}")
            print( "  Use --overwrite to regenerate, or skip to reuse the existing pack.")
            _separator()
            return 0
        else:
            print("  --overwrite set — regenerating DataPack.")
            _separator()

    # Generate
    t0 = time.monotonic()

    try:
        print("  Generating facility...", end="", flush=True)
        # We call generate() once — it does all domains internally.
        # For per-domain progress we print steps synchronously.
        from maiw_world.generator import WarehouseWorldGenerator
        gen = WarehouseWorldGenerator(config)
        result = gen.generate()
        elapsed = time.monotonic() - t0
    except Exception as exc:
        print(f"\nERROR during generation: {exc}", file=sys.stderr)
        return 1

    g = result.graph
    r = result.report

    # Print domain summary
    ec = r.entity_counts
    c = config
    print(f"\r  Generating facility...        done   ({c.facility.zone_count} zones, {c.facility.location_count} locations)")
    print(f"  Generating inventory...       done   ({c.inventory.sku_count:,} SKUs)")
    print(f"  Generating labor...           done   ({c.labor.workers_per_shift * c.labor.shift_count} workers)")
    print(f"  Generating equipment...       done   ({ec.equipment} units)")
    print(f"  Generating orders...          done   ({ec.orders} orders)")
    print(f"  Generating waves...           done   ({ec.waves} waves, {ec.tasks} tasks)")
    print(f"  Building historical events... done   ({g.event_count} events)")
    _separator()

    # Validate
    val_status = "PASS" if r.validation_result.passed else "FAIL"
    print(f"  Validating...                 {val_status}")
    _separator()

    if not r.validation_result.passed:
        print("FAIL — generated graph did not pass validation.", file=sys.stderr)
        return 1

    # Write DataPack
    try:
        WarehouseDataPack.write(g, config, output_dir)
    except Exception as exc:
        print(f"ERROR writing DataPack: {exc}", file=sys.stderr)
        return 1

    checksum = compute_semantic_checksum(g)
    duration_ms = elapsed * 1000

    print("  DataPack written:")
    _row("", str(output_dir), width=0)
    _separator()
    _row("  Entities", f"{g.entity_count:,}")
    _row("  Edges",    f"{g.edge_count:,}")
    _row("  Checksum", checksum[:16] + "...")
    _row("  Duration", f"{duration_ms:.0f} ms")
    _separator()

    return 0


# ── validate ──────────────────────────────────────────────────────────────────

def cmd_validate(args: argparse.Namespace) -> int:
    from maiw_world.datapack import WarehouseDataPack

    pack_dir = Path(args.pack_dir)

    _header("MAIW DataPack Validation")

    if not pack_dir.exists():
        print(f"ERROR: DataPack directory not found: {pack_dir}", file=sys.stderr)
        return 1

    # Read manifest for identity info
    try:
        manifest = WarehouseDataPack.read_manifest(pack_dir)
        warehouse_id = manifest.get("warehouse_id", "?")
        dataset_id   = manifest.get("dataset_id", "?")
        seed         = manifest.get("seed", "?")
    except Exception:
        warehouse_id = dataset_id = seed = "?"

    _row("DataPack",  str(pack_dir))
    _row("Dataset",   dataset_id)
    _row("Warehouse", warehouse_id)
    _row("Seed",      str(seed))
    _separator()

    result = WarehouseDataPack.verify(pack_dir)

    def _check(label: str, ok: bool) -> None:
        print(f"  {label:<20} {'PASS' if ok else 'FAIL'}")

    _check("Manifest",       result.manifest_valid)
    _check("File checksums", result.file_checksums_match)
    _check("Semantic check", result.semantic_checksum_match)
    gv = result.graph_validation
    _check("Graph validity", gv is not None and gv.passed)
    _separator()
    print(f"  {'Status':<20} {'PASS' if result.passed else 'FAIL'}")

    if not result.passed and result.errors:
        _separator()
        print("  Errors:")
        for e in result.errors:
            print(f"    - {e}")

    _separator()
    return 0 if result.passed else 1


# ── inspect ───────────────────────────────────────────────────────────────────

def cmd_inspect(args: argparse.Namespace) -> int:
    from maiw_world.datapack import WarehouseDataPack

    pack_dir = Path(args.pack_dir)
    if not pack_dir.exists():
        print(f"ERROR: DataPack not found: {pack_dir}", file=sys.stderr)
        return 1

    g = WarehouseDataPack.load(pack_dir)

    if args.entity:
        entity = g.get_entity(args.entity)
        if entity is None:
            print(f"ERROR: Entity not found: {args.entity}", file=sys.stderr)
            return 1
        _header(f"Entity: {entity.id}")
        data = entity.model_dump(mode="json")
        for k, v in sorted(data.items()):
            print(f"  {k:<30} {v}")
        _separator()

        out_edges = g.outgoing_edges(entity.id)
        if out_edges:
            print(f"  Outgoing edges ({len(out_edges)}):")
            for e in out_edges:
                print(f"    {e.id:<40}  {e.relationship_type.value:<20}  → {e.target_id}")
        else:
            print("  Outgoing edges: (none)")

        _separator()
        in_edges = g.incoming_edges(entity.id)
        if in_edges:
            print(f"  Incoming edges ({len(in_edges)}):")
            for e in in_edges:
                print(f"    {e.id:<40}  {e.relationship_type.value:<20}  ← {e.source_id}")
        else:
            print("  Incoming edges: (none)")

        _separator()
        return 0

    # Default: summary view
    _header("MAIW DataPack — Operational Graph Summary")
    summary = g.summary()
    _separator()
    print("  Entity counts:")
    for k, v in sorted((k, v) for k, v in summary.items() if k.startswith("entity_") and k != "entity_count"):
        label = k.replace("entity_", "")
        print(f"    {label:<30} {v:,}")
    print(f"    {'(total)':<30} {summary.get('entity_count', 0):,}")

    _separator()
    print("  Edge counts:")
    for k, v in sorted((k, v) for k, v in summary.items() if k.startswith("edge_") and k != "edge_count"):
        label = k.replace("edge_", "")
        print(f"    {label:<30} {v:,}")
    print(f"    {'(total)':<30} {summary.get('edge_count', 0):,}")

    _separator()
    print(f"  Historical events:             {summary.get('event_count', 0):,}")
    _separator()
    return 0


# ── scenarios ─────────────────────────────────────────────────────────────────

def cmd_scenarios(args: argparse.Namespace) -> int:
    from maiw_world.datapack import WarehouseDataPack
    from maiw_world.scenario import labor_constraint_scenario, equipment_failure_scenario, ScenarioOverlay
    from maiw_world.entities import EntityType

    pack_dir = Path(args.pack_dir)
    if not pack_dir.exists():
        print(f"ERROR: DataPack not found: {pack_dir}", file=sys.stderr)
        return 1

    g = WarehouseDataPack.load(pack_dir)

    _header("MAIW Available Scenarios")

    # DataPack-native scenarios
    native_scenarios = [
        ("labor_constraint_wave_risk", "labor_constraint",   lambda: labor_constraint_scenario(g)),
        ("equipment_failure",          "equipment_failure",  lambda: equipment_failure_scenario(g)),
        ("healthy_baseline",           "healthy_baseline",   None),
    ]
    # Compatibility scenarios
    compat_scenarios = [
        ("stale_state",   "Compatibility (healthy_baseline adapter)"),
        ("state_drift",   "Compatibility (healthy_baseline adapter)"),
    ]

    print(f"  {'Scenario':<35} {'Type':<30} {'Events'}")
    print(f"  {'-'*35} {'-'*30} {'-'*6}")

    for name, kind, factory in native_scenarios:
        if factory is not None:
            try:
                overlay = factory()
                event_count = len(overlay.events)
            except Exception:
                event_count = "?"
        else:
            event_count = 0
        kind_label = "DataPack-native"
        print(f"  {name:<35} {kind_label:<30} {event_count}")

    for name, kind_label in compat_scenarios:
        print(f"  {name:<35} {kind_label:<30} {'—'}")

    _separator()
    return 0


# ── checksum ──────────────────────────────────────────────────────────────────

def cmd_checksum(args: argparse.Namespace) -> int:
    from maiw_world.datapack import WarehouseDataPack

    pack_dir = Path(args.pack_dir)
    if not pack_dir.exists():
        print(f"ERROR: DataPack not found: {pack_dir}", file=sys.stderr)
        return 1

    _header("MAIW DataPack Checksums")
    _row("DataPack", str(pack_dir))
    _separator()

    try:
        manifest = WarehouseDataPack.read_manifest(pack_dir)
        semantic_cs = manifest.get("semantic_checksum", "?")
        _row("Semantic checksum", semantic_cs)
    except Exception as exc:
        print(f"ERROR reading manifest: {exc}", file=sys.stderr)
        return 1

    try:
        checksums_path = pack_dir / "checksums.json"
        if checksums_path.exists():
            data = json.loads(checksums_path.read_text(encoding="utf-8"))
            _separator()
            print("  File checksums:")
            for rel_path, cs in sorted(data.get("files", {}).items()):
                print(f"    {rel_path:<40} {cs}")
    except Exception as exc:
        print(f"ERROR reading checksums: {exc}", file=sys.stderr)
        return 1

    _separator()

    # Verify
    result = WarehouseDataPack.verify(pack_dir)
    print(f"  Verification: {'PASS' if result.passed else 'FAIL'}")
    _separator()
    return 0 if result.passed else 1


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m maiw_world",
        description="MAIW Warehouse World CLI",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate a Warehouse World DataPack")
    p_gen.add_argument("--config",    metavar="<yaml>", help="Path to world config YAML (default: dc47_demo preset)")
    p_gen.add_argument("--output",    metavar="<dir>",  help="Output directory for DataPack (default: data/worlds/<dataset_id>)")
    p_gen.add_argument("--overwrite", action="store_true", help="Overwrite existing DataPack")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate an existing DataPack")
    p_val.add_argument("pack_dir", metavar="<pack_dir>", help="Path to DataPack directory")

    # inspect
    p_ins = subparsers.add_parser("inspect", help="Inspect a DataPack's graph")
    p_ins.add_argument("pack_dir", metavar="<pack_dir>", help="Path to DataPack directory")
    p_ins.add_argument("--entity",  metavar="<id>",   help="Show a specific entity by ID")
    p_ins.add_argument("--summary", action="store_true", help="Show entity/edge summary (default)")

    # scenarios
    p_scen = subparsers.add_parser("scenarios", help="List available scenarios for a DataPack")
    p_scen.add_argument("pack_dir", metavar="<pack_dir>", help="Path to DataPack directory")

    # checksum
    p_cs = subparsers.add_parser("checksum", help="Print checksums for a DataPack")
    p_cs.add_argument("pack_dir", metavar="<pack_dir>", help="Path to DataPack directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "generate":  cmd_generate,
        "validate":  cmd_validate,
        "inspect":   cmd_inspect,
        "scenarios": cmd_scenarios,
        "checksum":  cmd_checksum,
    }

    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
