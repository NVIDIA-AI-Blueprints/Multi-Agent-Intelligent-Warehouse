# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Equipment domain state predicates (Proof SOP B).

These are the named predicates that decide whether an equipment recovery is
*actually* complete. They are the enforcement point for the single invariant
Proof SOP B exists to demonstrate:

    Equipment recovery is complete only when the physical/operational state
    proves the recovery — not when the agent, MCP server, or executor says
    it succeeded.

Design rules this module obeys:

  * **Named, not evaluated.** A SOP names a predicate; it can never supply an
    expression. There is no ``eval()`` here and no expression language in the
    YAML. See ``sop_engine/validators.py`` for the same rule applied to
    ``StepCondition``.
  * **Domain-registered, not engine-embedded.** The generic validator engine
    knows nothing about forklifts. Equipment semantics live in the equipment
    package and register themselves into the engine's registry at import time.
  * **Read-only and pure.** A predicate receives a plain ``dict`` view of
    authoritative warehouse state and returns a bool. It may not mutate state,
    call a capability, or reach the network.

Authority boundary: nothing in this module imports ``maiw_execution``, holds an
ActionExecutor, or performs a write. A predicate can only ever *observe*.

State shape
-----------
Predicates read the sealed ``WarehouseStateSnapshot`` as a dict (the SOP Engine
passes ``context.warehouse_state_snapshot`` through ``model_dump()``), i.e.::

    {"equipment": {"assets": [{"asset_id", "equipment_type", "status", "zone"}, ...]}}

Two producers of that view disagree on one key: ``maiw_state.models.equipment``
emits ``equipment_type`` while ``state_aware_ops.get_equipment_state_snapshot``
emits ``type``. These predicates only depend on ``asset_id``, ``status`` and
``zone``, which are spelled identically in both, so the disagreement does not
affect them. The mismatch is recorded as a known gap in
``docs/sops/EQUIPMENT_FAILURE_RECOVERY.md``.
"""

from __future__ import annotations

from typing import Any

from ..sop_engine.validators import register_predicate

__all__ = [
    "OPERATIONAL_STATUSES",
    "NON_OPERATIONAL_STATUSES",
    "EQUIPMENT_PREDICATES",
    "equipment_write_landed",
    "equipment_replacement_assigned",
    "equipment_recovery_complete",
    "register_equipment_predicates",
]


# Equipment status is an unenumerated ``str`` in maiw-state and maiw-contracts.
# These frozensets are the documented vocabulary from
# ``maiw_contracts/equipment.py`` — they are NOT a new enum, just the agreed
# reading of the existing strings.
OPERATIONAL_STATUSES = frozenset({"available", "assigned", "charging"})
NON_OPERATIONAL_STATUSES = frozenset({"offline", "maintenance"})


def _assets_by_id(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the equipment assets in an authoritative state view by asset_id."""
    equipment = state.get("equipment") or {}
    if not isinstance(equipment, dict):
        return {}
    assets = equipment.get("assets") or []
    if not isinstance(assets, list):
        return {}
    return {
        asset["asset_id"]: asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id")
    }


# ── The three predicates, in increasing order of strength ────────────────────


def equipment_write_landed(state: dict[str, Any], args: dict[str, Any]) -> bool:
    """
    Weakest proof: did the mutation reach the warehouse *at all*?

    This is the predicate evaluated at the governance-resume seam, which is the
    first moment post-write authoritative state exists. It deliberately asks the
    smallest answerable question — "has the replacement asset left the available
    pool?" — because that is what separates "the write is lost" from "the write
    landed but we cannot read the response".

    An ambiguous executor outcome (UNKNOWN / INDETERMINATE / TIMEOUT) is resolved
    here by *reading*, never by re-issuing the write. If this predicate holds,
    the ambiguous write is reconciled as CONFIRMED_EXECUTED. If it does not, the
    SOP Engine escalates EXECUTION_INDETERMINATE.

    args: replacement_asset_id
    """
    asset = _assets_by_id(state).get(args["replacement_asset_id"])
    if asset is None:
        return False
    return asset.get("status") != "available"


def equipment_replacement_assigned(state: dict[str, Any], args: dict[str, Any]) -> bool:
    """
    Stronger proof: did the mutation produce the *intended* transition?

    "Not available any more" is not the same as "assigned". An asset that went
    to ``maintenance`` or ``offline`` between the read and the write also left
    the available pool, and that is not the recovery we asked for.

    args: replacement_asset_id, expected_status (default "assigned")
    """
    asset = _assets_by_id(state).get(args["replacement_asset_id"])
    if asset is None:
        return False
    return asset.get("status") == args.get("expected_status", "assigned")


def equipment_recovery_complete(state: dict[str, Any], args: dict[str, Any]) -> bool:
    """
    Strongest proof: is the warehouse *objective* restored?

    Execution succeeding is not recovery succeeding. This is the operational
    post-condition, and all of it must hold simultaneously:

      1. the replacement asset carries the expected status (default "assigned");
      2. the replacement asset is in the zone that lost capacity, when a zone is
         named — a forklift assigned in the wrong aisle has not recovered
         anything;
      3. the failed asset has NOT silently returned to service. If the asset we
         declared failed is operational again, either the diagnosis was wrong or
         somebody re-enabled faulty equipment; both require a human.

    args: replacement_asset_id, failed_asset_id,
          expected_status (default "assigned"), expected_zone (optional)
    """
    assets = _assets_by_id(state)
    replacement = assets.get(args["replacement_asset_id"])
    failed = assets.get(args["failed_asset_id"])

    if replacement is None or failed is None:
        return False

    if replacement.get("status") != args.get("expected_status", "assigned"):
        return False

    expected_zone = args.get("expected_zone")
    if expected_zone is not None and replacement.get("zone") != expected_zone:
        return False

    # The failed asset must still be out of service.
    return failed.get("status") not in OPERATIONAL_STATUSES


# ── Registration ─────────────────────────────────────────────────────────────

EQUIPMENT_PREDICATES = {
    "equipment_write_landed": equipment_write_landed,
    "equipment_replacement_assigned": equipment_replacement_assigned,
    "equipment_recovery_complete": equipment_recovery_complete,
}


def register_equipment_predicates() -> None:
    """
    Register the equipment domain predicates with the SOP Engine.

    Idempotent — re-registering the same name rebinds it to the same function.
    Called at import of ``maiw_agents.equipment`` so that loading the equipment
    domain is what makes its predicates available, rather than the generic
    engine having to know equipment exists.
    """
    for name, fn in EQUIPMENT_PREDICATES.items():
        register_predicate(name, fn)


register_equipment_predicates()
