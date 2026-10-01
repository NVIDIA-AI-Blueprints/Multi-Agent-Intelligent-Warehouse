# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
RuntimeCapabilityPolicy — explicit, typed, deny-by-default capability boundary.

The invariant under test:

    A capability not named in the policy is denied, including one that did not
    exist when the policy was issued. WRITE and EMERGENCY_WRITE can never appear
    in any policy that can be constructed. And no sequence of retries, loops,
    governance pauses or restarts can widen a policy.

This is the contract a sandboxed executor (NemoClaw or otherwise) will be handed
instead of being trusted to restrain itself, so these tests are the boundary.
"""

from __future__ import annotations

import pytest

from conftest import ScriptedExecutor, make_sop
from maiw_agents.contracts.agent import AgentDefinition, GovernanceBoundary
from maiw_agents.contracts.capability_policy import (
    ALWAYS_DENIED_CAPABILITY_CLASSES,
    CapabilityDeniedError,
    RuntimeCapabilityPolicy,
    authorize_capability,
    authorize_step,
    authorize_subagent,
    build_capability_policy,
)
from maiw_agents.contracts.registry import CapabilityClass, SKILL_REGISTRY
from maiw_agents.contracts.runtime import AgentExecutionContext
from maiw_agents.contracts.sop import SOPDefinition, SOPStep
from maiw_agents.contracts.sop_v2 import EscalationReasonCode


# ── Helpers ───────────────────────────────────────────────────────────────────

def _caps_of_class(cls: CapabilityClass) -> list[str]:
    return sorted(
        cap_id for cap_id, entry in SKILL_REGISTRY.items()
        if entry.capability_class is cls
    )


READ_CAPS = _caps_of_class(CapabilityClass.READ)
ANALYTICAL_CAPS = _caps_of_class(CapabilityClass.ANALYTICAL)
PROPOSAL_CAPS = _caps_of_class(CapabilityClass.PROPOSAL)
WRITE_CAPS = _caps_of_class(CapabilityClass.WRITE) + _caps_of_class(
    CapabilityClass.EMERGENCY_WRITE
)


def _definition(
    *,
    capabilities: list[str] | None = None,
    subagents: list[str] | None = None,
    classes: list[str] | None = None,
) -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="test",
        domain="operations",
        allowed_capabilities=capabilities or [],
        allowed_subagents=subagents or [],
        output_contract="RecommendedAction",
        governance_boundary=GovernanceBoundary(
            allowed_capability_classes=classes or ["READ", "ANALYTICAL", "PROPOSAL"]
        ),
    )


def _sop(
    *,
    capabilities: list[str] | None = None,
    subagents: list[str] | None = None,
    steps: list[SOPStep] | None = None,
) -> SOPDefinition:
    return SOPDefinition(
        id="test.sop",
        version="1.0",
        agent="operations_coordination",
        objective="test",
        steps=steps or [SOPStep(id="a", action="read_wave_status")],
        stop_conditions=["objective_met"],
        allowed_capabilities=capabilities or [],
        allowed_subagents=subagents or [],
    )


def _policy(**overrides) -> RuntimeCapabilityPolicy:
    base = dict(
        agent_task_id="task-1",
        sop_id="test.sop",
        sop_version="1.0",
        runtime="deterministic",
        allowed_capability_ids=frozenset(),
        allowed_capability_classes=frozenset({"READ", "ANALYTICAL", "PROPOSAL"}),
        allowed_subagents=frozenset(),
    )
    base.update(overrides)
    return RuntimeCapabilityPolicy(**base)


def _built(**kwargs) -> RuntimeCapabilityPolicy:
    caps = kwargs.pop("capabilities", [])
    subs = kwargs.pop("subagents", [])
    classes = kwargs.pop("classes", None)
    return build_capability_policy(
        definition=_definition(capabilities=caps, subagents=subs, classes=classes),
        sop=_sop(capabilities=caps, subagents=subs),
        agent_task_id="task-1",
        runtime="deterministic",
        **kwargs,
    )


# ── Registry sanity: these tests are only meaningful if the classes exist ──────

def test_registry_actually_contains_each_class_under_test():
    assert READ_CAPS, "no READ capabilities registered — policy tests would be vacuous"
    assert ANALYTICAL_CAPS, "no ANALYTICAL capabilities registered"
    assert PROPOSAL_CAPS, "no PROPOSAL capabilities registered"
    assert WRITE_CAPS, "no WRITE capabilities registered — deny tests would be vacuous"


# ── 1–3: declared capabilities are allowed ────────────────────────────────────

@pytest.mark.asyncio
async def test_declared_read_capability_is_allowed():
    cap = READ_CAPS[0]
    policy = _built(capabilities=[cap])
    assert cap in policy.allowed_capability_ids
    await authorize_capability(policy, cap)   # must not raise


@pytest.mark.asyncio
async def test_declared_analytical_capability_is_allowed():
    cap = ANALYTICAL_CAPS[0]
    policy = _built(capabilities=[cap])
    await authorize_capability(policy, cap)


@pytest.mark.asyncio
async def test_declared_proposal_capability_is_allowed():
    cap = PROPOSAL_CAPS[0]
    policy = _built(capabilities=[cap])
    await authorize_capability(policy, cap)


# ── 4: deny-by-default ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_undeclared_capability_is_denied():
    """The core rule: absence from the allow-list is a denial, not a gap."""
    declared, undeclared = READ_CAPS[0], READ_CAPS[1]
    policy = _built(capabilities=[declared])

    with pytest.raises(CapabilityDeniedError) as exc:
        await authorize_capability(policy, undeclared)
    assert "allow-list" in exc.value.reason


@pytest.mark.asyncio
async def test_a_capability_that_does_not_exist_at_all_is_denied():
    """
    Deny-by-default covers the unknown, not just the disallowed.

    A capability MAIW cannot classify is one MAIW cannot vouch for, so it is
    refused rather than given the benefit of the doubt.
    """
    policy = _built(capabilities=[READ_CAPS[0]])
    with pytest.raises(CapabilityDeniedError) as exc:
        await authorize_capability(policy, "warehouse.totally.invented")
    assert "registry" in exc.value.reason


@pytest.mark.asyncio
async def test_an_empty_policy_denies_everything():
    policy = _policy()
    for cap in READ_CAPS[:3]:
        with pytest.raises(CapabilityDeniedError):
            await authorize_capability(policy, cap)


# ── 5–6: WRITE and EMERGENCY_WRITE are never permitted ────────────────────────

@pytest.mark.parametrize("write_cap", WRITE_CAPS)
@pytest.mark.asyncio
async def test_write_capabilities_are_always_denied(write_cap):
    entry = SKILL_REGISTRY[write_cap]
    policy = _policy()
    with pytest.raises(CapabilityDeniedError) as exc:
        await authorize_capability(policy, write_cap, entry.capability_class.value)
    assert "permanently denied" in exc.value.reason


def test_write_classes_are_denied_in_every_constructible_policy():
    policy = _policy()
    assert ALWAYS_DENIED_CAPABILITY_CLASSES <= policy.denied_capability_classes
    assert not (ALWAYS_DENIED_CAPABILITY_CLASSES & policy.allowed_capability_classes)


@pytest.mark.parametrize("write_class", sorted(ALWAYS_DENIED_CAPABILITY_CLASSES))
def test_a_policy_allowing_a_write_class_cannot_be_constructed(write_class):
    """Not a default that can be overridden — a rule the type system enforces."""
    with pytest.raises(ValueError, match="never allow"):
        _policy(
            allowed_capability_classes=frozenset({"READ", write_class}),
        )


@pytest.mark.parametrize("write_class", sorted(ALWAYS_DENIED_CAPABILITY_CLASSES))
def test_a_policy_omitting_a_write_class_from_the_deny_list_is_rejected(write_class):
    remaining = ALWAYS_DENIED_CAPABILITY_CLASSES - {write_class}
    with pytest.raises(ValueError, match="must deny"):
        _policy(denied_capability_classes=frozenset(remaining))


@pytest.mark.parametrize("write_cap", WRITE_CAPS)
def test_a_write_capability_id_cannot_be_smuggled_onto_the_allow_list(write_cap):
    """Naming the id must not sidestep the class deny-list."""
    with pytest.raises(ValueError, match="write capabilities are never permitted"):
        _policy(allowed_capability_ids=frozenset({write_cap}))


def test_builder_drops_a_write_capability_even_when_declared():
    cap = WRITE_CAPS[0]
    policy = _built(capabilities=[cap, READ_CAPS[0]])
    assert cap not in policy.allowed_capability_ids
    assert READ_CAPS[0] in policy.allowed_capability_ids


# ── 7–8: subagents ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_declared_subagent_is_allowed():
    policy = _built(subagents=["labor"])
    assert policy.permits_subagent("labor")
    await authorize_subagent(policy, "labor")


@pytest.mark.asyncio
async def test_undeclared_subagent_is_denied():
    policy = _built(subagents=["labor"])
    with pytest.raises(CapabilityDeniedError) as exc:
        await authorize_subagent(policy, "equipment")
    assert "allow-list" in exc.value.reason


@pytest.mark.asyncio
async def test_a_step_delegating_to_an_undeclared_subagent_is_denied():
    policy = _built(subagents=["labor"])
    step = SOPStep(id="d", action="delegate_to_agent", delegate_to="equipment")
    with pytest.raises(CapabilityDeniedError):
        await authorize_step(policy, step)


# ── 9: immutability ───────────────────────────────────────────────────────────

def test_policy_is_frozen():
    policy = _built(capabilities=[READ_CAPS[0]])
    with pytest.raises(Exception):   # pydantic ValidationError on a frozen model
        policy.allowed_capability_ids = frozenset({"anything"})
    with pytest.raises(Exception):
        policy.policy_id = "tampered"


def test_policy_collections_are_frozensets_not_mutable_sets():
    """
    Frozen model + mutable members would still be mutable. Both halves matter.
    """
    policy = _built(capabilities=[READ_CAPS[0]], subagents=["labor"])
    for collection in (
        policy.allowed_capability_ids,
        policy.allowed_capability_classes,
        policy.denied_capability_classes,
        policy.allowed_subagents,
    ):
        assert isinstance(collection, frozenset)
        with pytest.raises(AttributeError):
            collection.add("smuggled")


# ── Construction inputs ───────────────────────────────────────────────────────

def test_policy_is_the_intersection_of_agent_and_sop_allow_lists():
    """A SOP naming a capability the agent lacks does not grant it."""
    agent_cap, sop_only_cap = READ_CAPS[0], READ_CAPS[1]
    policy = build_capability_policy(
        definition=_definition(capabilities=[agent_cap]),
        sop=_sop(capabilities=[agent_cap, sop_only_cap]),
        agent_task_id="task-1",
        runtime="deterministic",
    )
    assert agent_cap in policy.allowed_capability_ids
    assert sop_only_cap not in policy.allowed_capability_ids


def test_governance_boundary_narrows_the_class_allow_list():
    """An agent restricted to READ does not get its PROPOSAL capabilities."""
    read_cap, proposal_cap = READ_CAPS[0], PROPOSAL_CAPS[0]
    policy = _built(capabilities=[read_cap, proposal_cap], classes=["READ"])
    assert policy.allowed_capability_classes == frozenset({"READ"})
    assert read_cap in policy.allowed_capability_ids
    assert proposal_cap not in policy.allowed_capability_ids


def test_policy_pins_the_sop_version_it_was_issued_for():
    policy = _built(capabilities=[READ_CAPS[0]])
    assert policy.sop_id == "test.sop"
    assert policy.sop_version == "1.0"
    assert policy.agent_task_id == "task-1"
    assert policy.runtime == "deterministic"


def test_unregistered_capabilities_are_dropped_not_trusted():
    policy = _built(capabilities=[READ_CAPS[0], "warehouse.invented.capability"])
    assert "warehouse.invented.capability" not in policy.allowed_capability_ids


# ── 10–12: recovery and no privilege expansion ────────────────────────────────

def test_policy_rebuilt_after_a_restart_is_identical():
    """
    A restored procedure gets the same authority it had, not more.

    Policies are derived, not stored: rebuilding from the same AgentDefinition,
    SOP and registry must produce the same grants. Only policy_id and issued_at
    differ, because they identify the instance rather than the authority.
    """
    before = _built(capabilities=READ_CAPS[:2], subagents=["labor"])
    after = _built(capabilities=READ_CAPS[:2], subagents=["labor"])

    assert after.allowed_capability_ids == before.allowed_capability_ids
    assert after.allowed_capability_classes == before.allowed_capability_classes
    assert after.denied_capability_classes == before.denied_capability_classes
    assert after.allowed_subagents == before.allowed_subagents
    after.assert_not_broadened(before)


def test_is_narrower_or_equal_to_detects_a_broadened_policy():
    baseline = _built(capabilities=[READ_CAPS[0]])
    broadened = _built(capabilities=READ_CAPS[:2])

    assert baseline.is_narrower_or_equal_to(broadened)
    assert not broadened.is_narrower_or_equal_to(baseline)
    with pytest.raises(CapabilityDeniedError, match="broadened"):
        broadened.assert_not_broadened(baseline)


def test_a_policy_gaining_a_subagent_is_detected_as_broadened():
    baseline = _built(subagents=["labor"])
    broadened = _built(subagents=["labor", "wave"])
    with pytest.raises(CapabilityDeniedError, match="broadened"):
        broadened.assert_not_broadened(baseline)


@pytest.mark.asyncio
async def test_no_privilege_expansion_across_the_full_lifecycle():
    """
    start → loop → retry → governance pause → restart → resume.

    At every checkpoint the live policy must be equal to or narrower than the
    one issued at the start. This is the test that says authority cannot grow
    by outlasting the code that granted it.
    """
    from maiw_agents.runtime.deterministic import MAIWDeterministicRuntime
    from maiw_agents.contracts.task import AgentTaskState
    from maiw_agents.sop_engine import InMemoryProcedureStateStore

    caps = READ_CAPS[:2]
    definition = _definition(capabilities=caps, subagents=["labor"])
    sop = _sop(
        capabilities=caps,
        subagents=["labor"],
        steps=[
            SOPStep(id="one", action="read_wave_status", next_step_id="two"),
            SOPStep(id="two", action="return_wave_assessment"),
        ],
    )

    baseline = build_capability_policy(
        definition=definition, sop=sop, agent_task_id="task-1", runtime="deterministic"
    )

    store = InMemoryProcedureStateStore()
    checkpoints: list[RuntimeCapabilityPolicy] = []

    for phase in ("start", "retry", "governance_resume", "restart"):
        runtime = MAIWDeterministicRuntime(store=store)
        state = AgentTaskState(
            task_id="task-1",
            agent_id=definition.agent_id,
            objective=definition.objective,
            sop_id=sop.id,
            sop_version=sop.version,
        )
        await runtime.run_task(
            definition, sop, state,
            AgentExecutionContext(warehouse_id="wh", trace_id=f"t-{phase}"),
        )
        assert runtime._policy is not None
        checkpoints.append(runtime._policy)

    for phase_policy in checkpoints:
        phase_policy.assert_not_broadened(baseline)
        assert phase_policy.allowed_capability_ids == baseline.allowed_capability_ids
        assert not (
            ALWAYS_DENIED_CAPABILITY_CLASSES & phase_policy.allowed_capability_classes
        )


# ── Enforcement inside the runtimes ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_deterministic_runtime_denies_an_undeclared_skill_at_invocation():
    """
    The gate is at invocation, not only at load time.

    The SOP declares nothing, so the step's skill is not on the policy's
    allow-list — and the step escalates as CAPABILITY_DENIED rather than
    quietly running.
    """
    from maiw_agents.runtime.deterministic import MAIWDeterministicRuntime
    from maiw_agents.contracts.task import AgentTaskState

    step = SOPStep(id="s", action="invoke_skill", skill_id=READ_CAPS[0])
    sop = _sop(capabilities=[], steps=[step])
    definition = _definition(capabilities=[])

    runtime = MAIWDeterministicRuntime()
    result = await runtime.run_task(
        definition, sop,
        AgentTaskState(
            task_id="t", agent_id=definition.agent_id,
            objective=definition.objective,
            sop_id=sop.id, sop_version=sop.version,
        ),
        AgentExecutionContext(warehouse_id="wh", trace_id="t"),
    )
    assert result.final_status.value in ("ESCALATED", "FAILED")
    assert "denied" in (result.escalation_reason or "").lower()


@pytest.mark.asyncio
async def test_deterministic_runtime_allows_a_declared_skill():
    from maiw_agents.runtime.deterministic import MAIWDeterministicRuntime
    from maiw_agents.contracts.task import AgentTaskState

    cap = READ_CAPS[0]
    step = SOPStep(id="s", action="invoke_skill", skill_id=cap)
    sop = _sop(capabilities=[cap], steps=[step])
    definition = _definition(capabilities=[cap])

    runtime = MAIWDeterministicRuntime()
    result = await runtime.run_task(
        definition, sop,
        AgentTaskState(
            task_id="t", agent_id=definition.agent_id,
            objective=definition.objective,
            sop_id=sop.id, sop_version=sop.version,
        ),
        AgentExecutionContext(warehouse_id="wh", trace_id="t"),
    )
    assert result.final_status.value == "COMPLETED"


@pytest.mark.asyncio
async def test_both_runtimes_share_one_authorization_implementation():
    """
    Section 17: no separate capability logic that can drift between runtimes.

    Both runtimes import the same ``authorize_step`` symbol. This asserts
    identity, not equivalence — there is nothing to drift because there is one
    function.
    """
    from maiw_agents.runtime import deep_agents_runtime, deterministic
    from maiw_agents.contracts import capability_policy

    assert deterministic.authorize_step is capability_policy.authorize_step
    assert deep_agents_runtime.authorize_step is capability_policy.authorize_step
    assert (
        deterministic.build_capability_policy
        is capability_policy.build_capability_policy
    )
    assert (
        deep_agents_runtime.build_capability_policy
        is capability_policy.build_capability_policy
    )


@pytest.mark.asyncio
async def test_deep_agents_tool_surface_is_derived_from_the_policy():
    """The model's tools and the enforcement gate read the same artifact."""
    from maiw_agents.runtime.deep_agents_runtime import _build_maiw_tools

    allowed, denied = READ_CAPS[0], READ_CAPS[1]
    policy = _built(capabilities=[allowed])
    context = AgentExecutionContext(warehouse_id="wh", trace_id="t")

    tools = _build_maiw_tools(context, [allowed, denied], policy)
    names = {t.name for t in tools}
    assert denied.replace(".", "_") not in names


@pytest.mark.asyncio
async def test_authorize_step_covers_every_capability_surface_of_a_step():
    """skill_id, the completion's required capability result, and delegate_to."""
    from maiw_agents.contracts.sop_v2 import StepCompletionSpec, ValidatorType

    allowed, denied = READ_CAPS[0], READ_CAPS[1]
    policy = _built(capabilities=[allowed], subagents=["labor"])

    # A step consuming a denied capability's result is using that capability.
    step = SOPStep(
        id="s", action="invoke_skill", skill_id=allowed,
        completion=StepCompletionSpec(
            validator_type=ValidatorType.CAPABILITY_RESULT,
            required_capability_result=denied,
        ),
    )
    with pytest.raises(CapabilityDeniedError):
        await authorize_step(policy, step)


# ── Escalation code ───────────────────────────────────────────────────────────

def test_capability_denied_has_its_own_escalation_reason():
    assert EscalationReasonCode.CAPABILITY_DENIED.value == "capability_denied"
