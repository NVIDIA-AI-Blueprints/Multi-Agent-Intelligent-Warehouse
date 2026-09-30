# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Inventory domain state predicates (Proof SOP C).

These are the named predicates that decide whether a picking/inventory
exception has *actually* cleared. They are the enforcement point for the two
invariants Proof SOP C exists to demonstrate:

    A picking exception is resolved only when authoritative inventory state
    proves it — not when an adjustment was submitted, approved, or reported
    successful.

    The SOP Engine controls the bounded reassessment loop. These predicates
    supply the verdict the engine acts on; they never decide how many times to
    look, and they are never asked whether to look again.

Design rules this module obeys (identical to ``maiw_agents/equipment/predicates.py``):

  * **Named, not evaluated.** A SOP names a predicate; it can never supply an
    expression. There is no ``eval()`` here and no expression language in the
    YAML. See ``sop_engine/validators.py`` for the same rule applied to
    ``StepCondition``.
  * **Domain-registered, not engine-embedded.** The generic validator engine
    knows nothing about SKUs. Inventory semantics live in the inventory package
    and register themselves into the engine's registry at import time.
  * **Read-only and pure.** A predicate receives a plain ``dict`` view of
    authoritative warehouse state and returns a bool. It may not mutate state,
    call a capability, or reach the network.

Authority boundary: nothing in this module imports ``maiw_execution``, holds an
ActionExecutor, or performs a write. A predicate can only ever *observe*. In
particular, no predicate here can adjust a count to make itself true.

State shape
-----------
Predicates read the sealed ``WarehouseStateSnapshot`` as a dict (the SOP Engine
passes ``context.warehouse_state_snapshot`` through ``model_dump()``), i.e.::

    {"inventory": {"items": [{"sku", "total_available", "is_low_stock",
                              "location_count"}, ...],
                   "total_items", "low_stock_count"}}

Two producers of that view spell the same facts differently, and both are
tolerated below:

    maiw_state.models.inventory.InventoryItemSummary
        sku / total_available / is_low_stock / location_count
    maiw_world.projections.InventoryItemProjection
        sku_id / quantity_available / is_low_stock  (no location_count; it is
        one row per location rather than an aggregate)

Known gap, deliberately not depended upon by default: the two producers also
disagree on the low-stock threshold — ``apps/api/maiw_api/demo/world.py``
computes ``quantity_available <= reorder_point`` while
``maiw_world/projections.py`` computes ``< reorder_point``. Because that
boundary case is ambiguous, ``is_low_stock`` is consulted only when a SOP opts
in via ``require_not_low_stock``. The default resolution criterion rests on
quantities and location counts, which both producers agree on. Recorded in
docs/sops/PICKING_INVENTORY_EXCEPTION.md.
"""

from __future__ import annotations

from typing import Any

from ..sop_engine.validators import register_predicate

__all__ = [
    "INVENTORY_STATE_KEYS",
    "SKU_KEYS",
    "AVAILABLE_KEYS",
    "INVENTORY_PREDICATES",
    "inventory_write_landed",
    "inventory_quantity_sufficient",
    "inventory_exception_resolved",
    "register_inventory_predicates",
]


# ``WarehouseState.inventory`` is singular. The tuple exists so a sealed
# snapshot and a bare state dict are both readable, mirroring WAVE_STATE_KEYS.
INVENTORY_STATE_KEYS = ("inventory",)

# The two spellings each producer uses for the same field. Order is preference
# order: the maiw-state contract spelling wins when both are present.
SKU_KEYS = ("sku", "sku_id")
AVAILABLE_KEYS = ("total_available", "quantity_available")


def _inventory_view(state: dict[str, Any]) -> dict[str, Any] | None:
    """
    Extract the inventory sub-view from an authoritative state dict.

    Returns ``None`` — never an empty dict — when there is no inventory data, so
    that "we could not read inventory" stays distinguishable from "inventory
    exists and this SKU is at zero". Missing data must never be read as proof:
    every predicate below treats ``None`` as "not proven".

    Unwraps the one level of nesting a sealed ``WarehouseStateSnapshot``
    introduces (``{"state": {"inventory": ...}}``).
    """
    if not isinstance(state, dict):
        return None

    for source in (state, state.get("state")):
        if not isinstance(source, dict):
            continue
        for key in INVENTORY_STATE_KEYS:
            view = source.get(key)
            if isinstance(view, dict):
                return view
    return None


def _non_negative_int(value: Any) -> int | None:
    """
    Read a count, or ``None`` if it is not one.

    ``bool`` is rejected explicitly: it is a subclass of ``int`` in Python, and
    ``total_available=True`` must not be silently read as "one unit on hand".
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first of ``keys`` present in ``item``, else ``None``."""
    for key in keys:
        if key in item:
            return item[key]
    return None


def _item_for_sku(state: dict[str, Any], sku: str) -> dict[str, Any] | None:
    """
    Find the inventory record for one SKU in an authoritative state view.

    When a producer emits one row per location rather than an aggregate, the
    rows for the SKU are summed so callers see a single consistent record.
    Returns ``None`` when the SKU is absent — which is not the same as a SKU
    present at zero, and the two must not be conflated.
    """
    view = _inventory_view(state)
    if view is None:
        return None

    items = view.get("items")
    if not isinstance(items, list):
        return None

    matching = [
        item
        for item in items
        if isinstance(item, dict) and _first_present(item, SKU_KEYS) == sku
    ]
    if not matching:
        return None

    if len(matching) == 1:
        return matching[0]

    # Per-location rows: aggregate into the shape the predicates expect.
    total = 0
    for row in matching:
        quantity = _non_negative_int(_first_present(row, AVAILABLE_KEYS))
        if quantity is None:
            return None
        total += quantity
    return {
        "sku": sku,
        "total_available": total,
        "location_count": len(matching),
        "is_low_stock": any(bool(row.get("is_low_stock")) for row in matching),
    }


def _available(item: dict[str, Any]) -> int | None:
    return _non_negative_int(_first_present(item, AVAILABLE_KEYS))


def _required_quantity(args: dict[str, Any]) -> int | None:
    """
    Read the declared requirement.

    A requirement below 1 is rejected rather than trivially satisfied: a SOP
    asking whether zero units are available is asking for no proof at all.
    """
    required = _non_negative_int(args.get("required_quantity"))
    if required is None or required < 1:
        return None
    return required


# ── The three predicates, in increasing order of strength ────────────────────


def inventory_write_landed(state: dict[str, Any], args: dict[str, Any]) -> bool:
    """
    Weakest proof: did the adjustment reach the warehouse *at all*?

    This is the predicate evaluated at the governance-resume seam, which is the
    first moment post-write authoritative state exists. It deliberately asks the
    smallest answerable question — "has availability for this SKU moved off the
    number we recorded before the write?" — because that is what separates "the
    adjustment was lost" from "the adjustment landed but we cannot read the
    response".

    An ambiguous executor outcome (UNKNOWN / INDETERMINATE / TIMEOUT) is resolved
    here by *reading*, never by re-issuing the adjustment. If this predicate
    holds, the ambiguous write is reconciled as CONFIRMED_EXECUTED. If it does
    not, the SOP Engine escalates EXECUTION_INDETERMINATE.

    Deliberately direction-agnostic: any movement away from the recorded
    baseline is evidence the write landed. Whether it moved the *right* way is
    the next predicate's question.

    args: sku, baseline_available
    """
    item = _item_for_sku(state, args["sku"])
    if item is None:
        return False

    observed = _available(item)
    baseline = _non_negative_int(args.get("baseline_available"))
    if observed is None or baseline is None:
        return False

    return observed != baseline


def inventory_quantity_sufficient(state: dict[str, Any], args: dict[str, Any]) -> bool:
    """
    Stronger proof: did the adjustment produce the *intended* quantity?

    "Something changed" is not the same as "enough is on hand". A cycle count
    that revised availability *down*, or a partial replenishment, also moves the
    number off its baseline, and neither resolves the pick.

    args: sku, required_quantity
    """
    item = _item_for_sku(state, args["sku"])
    if item is None:
        return False

    observed = _available(item)
    required = _required_quantity(args)
    if observed is None or required is None:
        return False

    return observed >= required


def inventory_exception_resolved(state: dict[str, Any], args: dict[str, Any]) -> bool:
    """
    Strongest proof: can the pick actually resume?

    This is the operational post-condition and the exit criterion of the bounded
    reassessment loop. All of it must hold simultaneously:

      1. availability meets the required quantity (as above);
      2. the SKU is held in at least ``min_locations`` locations. A record
         claiming stock with nowhere to pick it from is an inconsistent state,
         not a resolution — it is precisely the case a picker walks into. The
         engine must escalate that to a human rather than let a model reconcile
         it;
      3. optionally, the SKU is no longer flagged low-stock. Opt-in only, via
         ``require_not_low_stock``: the two producers of ``is_low_stock``
         disagree on the boundary case (see the module docstring), so a SOP must
         ask for that check knowingly.

    Returning False here does NOT decide anything about the loop. It reports
    that the exception has not cleared; whether that means "look again" or
    "escalate to a human" is the SOP Engine's decision, bounded by the step's
    declared LoopPolicy. This function cannot see the iteration count and cannot
    influence it.

    args: sku, required_quantity, min_locations (default 1),
          require_not_low_stock (default False)
    """
    item = _item_for_sku(state, args["sku"])
    if item is None:
        return False

    observed = _available(item)
    required = _required_quantity(args)
    if observed is None or required is None:
        return False

    if observed < required:
        return False

    min_locations = _non_negative_int(args.get("min_locations", 1))
    if min_locations is None:
        return False
    if min_locations > 0:
        location_count = _non_negative_int(item.get("location_count"))
        if location_count is None or location_count < min_locations:
            return False

    if args.get("require_not_low_stock", False):
        if bool(item.get("is_low_stock", False)):
            return False

    return True


# ── Registration ─────────────────────────────────────────────────────────────

INVENTORY_PREDICATES = {
    "inventory_write_landed": inventory_write_landed,
    "inventory_quantity_sufficient": inventory_quantity_sufficient,
    "inventory_exception_resolved": inventory_exception_resolved,
}


def register_inventory_predicates() -> None:
    """
    Register the inventory domain predicates with the SOP Engine.

    Idempotent — re-registering the same name rebinds it to the same function.
    Called at import of ``maiw_agents.inventory`` so that loading the inventory
    domain is what makes its predicates available, rather than the generic
    engine having to know inventory exists. Mirrors
    ``register_equipment_predicates()`` exactly.
    """
    for name, fn in INVENTORY_PREDICATES.items():
        register_predicate(name, fn)


register_inventory_predicates()
