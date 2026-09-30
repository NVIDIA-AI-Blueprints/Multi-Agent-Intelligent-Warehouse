# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Wave domain state predicates (Proof SOP A).

``wave_risk_resolution.v2.yaml`` — Proof SOP A — ends on a step whose completion
criterion is a named STATE_PREDICATE, ``wave_risk_reduced``. Until this module
existed that name resolved to nothing: the SOP was executable, the step was
reachable, and the validator returned ``unknown predicate`` (non-retryable) at
runtime. This module is the production owner of that name.

The invariant it enforces is the same one Proof SOP B enforces for equipment:

    A wave is resolved only when authoritative wave state says so — not when
    governance returned APPROVED, not when the executor returned a success
    string, and not because a recommendation was produced.

Design rules this module obeys (identical to
``maiw_agents/equipment/predicates.py``):

  * **Named, not evaluated.** A SOP names a predicate; it can never supply an
    expression. There is no ``eval()`` here and no expression language in the
    YAML.
  * **Domain-registered, not engine-embedded.** The generic validator engine
    knows nothing about waves, carrier cutoffs or OTIF. Wave semantics live in
    the wave package and register themselves into the engine's registry at
    import time.
  * **Read-only and pure.** A predicate receives a plain ``dict`` view of
    authoritative warehouse state and returns a bool. It may not mutate state,
    call a capability, or reach the network.

Authority boundary: nothing in this module imports ``maiw_execution``, holds an
ActionExecutor, a ModelGateway or an MCP client, or performs a write. A
predicate can only ever *observe*.

State shape
-----------
Predicates read the sealed ``WarehouseStateSnapshot`` as a dict (the SOP Engine
passes ``context.warehouse_state_snapshot`` through ``model_dump()``). The wave
component is ``maiw_state.models.wave.WaveState``::

    {"waves": {"warehouse_id": ..., "at_risk_count": int, "total_tasks": int,
               "pending_count": int, "tasks": [...], ...}}

Two spellings are accepted for that key. ``maiw_state.warehouse.WarehouseState``
declares the field as ``waves`` (plural, alongside ``inventory`` / ``equipment``
/ ``labor``), while wave-domain producers and the SOP prose say ``wave``. Both
are read; ``waves`` wins when both are present. A sealed
``WarehouseStateSnapshot.model_dump()` nests the domains one level deeper under
``state``, so that nesting is unwrapped too. This is deliberate tolerance of two
*known* shapes, not a general search: an unrecognised shape yields no wave view
and the predicate returns False.

Why there is no "before" snapshot here
--------------------------------------
``wave_risk_reduced`` evaluates *current* authoritative state only. It never
reads a pre-action snapshot, a cached model output, the recommendation text, or
the executor's return value — all four are claims about the world rather than
the world. When a SOP wants a relative statement ("at least N fewer than we
started with"), the baseline is supplied as a **declared literal** in
``predicate_args`` (the same class of thing as equipment's ``expected_status``),
so it is part of the procedure's authored expectation and auditable in the YAML,
rather than a value smuggled in from an earlier read.
"""

from __future__ import annotations

from typing import Any

from ..sop_engine.validators import register_predicate

__all__ = [
    "WAVE_STATE_KEYS",
    "WAVE_PREDICATES",
    "wave_risk_reduced",
    "register_wave_predicates",
]


# The two accepted spellings of the wave component in an authoritative state
# view, in precedence order. See the module docstring.
WAVE_STATE_KEYS = ("waves", "wave")


def _wave_view(state: dict[str, Any]) -> dict[str, Any] | None:
    """
    Extract the wave component from an authoritative state view.

    Returns ``None`` — never an empty dict — when no wave component is present,
    so that "no wave data" is distinguishable from "wave data with zero tasks".
    Missing data must never be read as proof.
    """
    if not isinstance(state, dict):
        return None

    candidates: list[dict[str, Any]] = [state]
    # A sealed WarehouseStateSnapshot nests WarehouseState under "state".
    nested = state.get("state")
    if isinstance(nested, dict):
        candidates.append(nested)

    for scope in candidates:
        for key in WAVE_STATE_KEYS:
            wave = scope.get(key)
            if isinstance(wave, dict):
                return wave
    return None


def _non_negative_int(value: Any) -> int | None:
    """
    Coerce a required count to ``int``, or ``None`` if it is not one.

    ``bool`` is rejected explicitly: it is an ``int`` subclass in Python, and
    ``at_risk_count=True`` must not be silently read as "one task at risk".
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def wave_risk_reduced(state: dict[str, Any], args: dict[str, Any]) -> bool:
    """
    Did the approved intervention actually take the wave out of risk?

    This is the operational post-condition for Proof SOP A's ``observe`` step.
    It reads exactly one authoritative field — ``waves.at_risk_count``, the
    OTIF-at-risk task count projected by ``WaveState`` — and answers in one of
    two modes:

    **Absolute (default).** With no declared baseline, the only statement a
    single reading of current state can support is that the wave is no longer in
    breach: ``at_risk_count <= max_at_risk_count`` (default ``0``). This is the
    SOP's stated objective — "restore an at-risk wave to on-track completion" —
    and it is deliberately the conservative reading. A partial improvement is
    not a resolution, and the step escalates for human review rather than
    completing.

    **Relative.** When the SOP declares ``baseline_at_risk_count``, the
    predicate requires ``baseline - current >= min_reduction``. The baseline is
    an authored literal in the YAML, not a prior snapshot read (see the module
    docstring).

    Missing-data behaviour — every one of these returns ``False``, never
    ``True``:

      * no wave component in the state view at all;
      * ``at_risk_count`` absent, non-integer, boolean, or negative;
      * ``min_reduction`` non-integer or ``< 1`` (a SOP asking for a reduction
        of zero is asking for no proof, which must not be read as proof);
      * ``max_at_risk_count`` non-integer or negative;
      * ``baseline_at_risk_count`` declared but not a non-negative integer;
      * ``warehouse_id`` declared in args and not matching the observed state.

    args:
        min_reduction (int, default 1)
            Minimum reduction required in relative mode; must be >= 1.
        baseline_at_risk_count (int, optional)
            Declared pre-intervention at-risk count. Switches to relative mode.
        max_at_risk_count (int, default 0)
            Absolute-mode ceiling on the remaining at-risk count.
        warehouse_id (str, optional)
            When declared, the observed wave state must belong to it.
    """
    wave = _wave_view(state)
    if wave is None:
        return False

    expected_warehouse_id = args.get("warehouse_id")
    if (
        expected_warehouse_id is not None
        and wave.get("warehouse_id") != expected_warehouse_id
    ):
        return False

    current = _non_negative_int(wave.get("at_risk_count"))
    if current is None:
        return False

    min_reduction = _non_negative_int(args.get("min_reduction", 1))
    if min_reduction is None or min_reduction < 1:
        return False

    baseline_arg = args.get("baseline_at_risk_count")
    if baseline_arg is not None:
        baseline = _non_negative_int(baseline_arg)
        if baseline is None:
            return False
        return (baseline - current) >= min_reduction

    max_at_risk = _non_negative_int(args.get("max_at_risk_count", 0))
    if max_at_risk is None:
        return False
    return current <= max_at_risk


# ── Registration ─────────────────────────────────────────────────────────────

WAVE_PREDICATES = {
    "wave_risk_reduced": wave_risk_reduced,
}


def register_wave_predicates() -> None:
    """
    Register the wave domain predicates with the SOP Engine.

    Idempotent — re-registering the same name rebinds it to the same function.
    Called at import of ``maiw_agents.wave`` so that loading the wave domain is
    what makes its predicates available, rather than the generic engine having
    to know waves exist. Mirrors ``register_equipment_predicates()`` exactly.
    """
    for name, fn in WAVE_PREDICATES.items():
        register_predicate(name, fn)


register_wave_predicates()
