# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW runtime capability boundary — explicit, typed, deny-by-default.

Before this contract existed, "what may this runtime do?" was answered by three
separate mechanisms that each covered part of the question: a load-time
alignment check, a tool-list filter in the Deep Agents runtime, and an action
name blacklist in the deterministic runtime. None of them was a single artifact
you could hold, log, restore after a crash, or compare against a later one to
prove authority had not grown.

``RuntimeCapabilityPolicy`` is that artifact.

    The policy is the complete answer to "what is this runtime permitted to
    invoke?" — and it is an allow-list. A capability that is not named in it is
    denied, including one that did not exist when the policy was issued.

Three properties are load-bearing:

  IMMUTABLE       ``frozen=True`` with frozenset members. A runtime handed a
                  policy cannot widen it, and neither can a model that
                  persuades a runtime to try.

  MAIW-AUTHORED   built only from AgentDefinition, SOPDefinition and the
                  capability registry — artifacts MAIW controls and reviews.
                  Never from model output, a prompt, an environment variable, or
                  anything a sandbox declares about itself.

  WRITE-FREE      WRITE and EMERGENCY_WRITE are denied unconditionally and
                  cannot be argued out of the policy by any input. Writes reach
                  the warehouse through governance → ActionExecutor → MCP, a
                  path that does not pass through any runtime.

This module is the sandbox-facing boundary contract. When NemoClaw (or any
other sandboxed executor) is integrated, it is handed a policy and the
``authorize_capability`` seam — not a wider surface it must be trusted to
restrain itself within.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent import AgentDefinition
from .registry import CapabilityClass, SKILL_REGISTRY
from .sop import SOPDefinition

logger = logging.getLogger(__name__)


# ── Permanently denied classes ────────────────────────────────────────────────

ALWAYS_DENIED_CAPABILITY_CLASSES: frozenset[str] = frozenset({
    CapabilityClass.WRITE.value,
    CapabilityClass.EMERGENCY_WRITE.value,
})
"""
Classes no policy may ever permit, regardless of what any input requests.

This is not a default that a caller may override. ``build_capability_policy``
re-adds these to ``denied_capability_classes`` after every other input has been
considered, and the model validator rejects any policy that tried to allow one.
"""

_INVOCABLE_CAPABILITY_CLASSES: frozenset[str] = frozenset({
    CapabilityClass.READ.value,
    CapabilityClass.ANALYTICAL.value,
    CapabilityClass.PROPOSAL.value,
})


class CapabilityDeniedError(PermissionError):
    """
    A runtime attempted a capability its policy does not permit.

    Raised at the invocation seam, not at load time. Load-time validation
    catches a badly-declared SOP; this catches everything else — a runtime bug,
    a model that talked a tool into firing, a capability added to the registry
    after the policy was issued.
    """

    def __init__(
        self,
        *,
        capability_id: str,
        capability_class: str | None,
        policy_id: str,
        reason: str,
    ) -> None:
        self.capability_id = capability_id
        self.capability_class = capability_class
        self.policy_id = policy_id
        self.reason = reason
        super().__init__(
            f"Capability {capability_id!r} (class={capability_class}) denied by "
            f"policy {policy_id}: {reason}"
        )


# ── Policy ────────────────────────────────────────────────────────────────────

class RuntimeCapabilityPolicy(BaseModel):
    """
    The immutable set of capabilities and subagents one runtime may invoke for
    one agent task under one SOP version.

    Scope is deliberately narrow — the policy is pinned to a task *and* a SOP
    version. A different SOP version gets a different policy, so a procedure
    restored after a restart cannot pick up authority from a SOP that was
    edited in the meantime.
    """

    model_config = ConfigDict(frozen=True)

    policy_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID4 identifying this exact policy instance.",
    )
    policy_revision: int = Field(
        default=1,
        ge=1,
        description=(
            "Increments only if a policy is deliberately re-issued for the same "
            "task. A restored procedure reuses the same revision — see "
            "assert_not_broadened()."
        ),
    )

    agent_task_id: str
    sop_id: str
    sop_version: str
    runtime: str = Field(description="'deterministic' | 'deep_agents' | a test name.")

    allowed_capability_ids: frozenset[str] = Field(default_factory=frozenset)
    allowed_capability_classes: frozenset[str] = Field(default_factory=frozenset)
    denied_capability_classes: frozenset[str] = Field(
        default_factory=lambda: ALWAYS_DENIED_CAPABILITY_CLASSES
    )
    allowed_subagents: frozenset[str] = Field(default_factory=frozenset)

    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _write_is_never_permitted(self) -> "RuntimeCapabilityPolicy":
        """
        WRITE and EMERGENCY_WRITE are denied in every policy that can exist.

        Constructed here rather than in the builder so that a hand-built policy
        — in a test, or in future sandbox glue code — cannot skip the rule by
        bypassing ``build_capability_policy``.
        """
        leaked = ALWAYS_DENIED_CAPABILITY_CLASSES & self.allowed_capability_classes
        if leaked:
            raise ValueError(
                f"RuntimeCapabilityPolicy may never allow {sorted(leaked)}. Writes "
                "cross the governance boundary, not a runtime."
            )

        missing = ALWAYS_DENIED_CAPABILITY_CLASSES - self.denied_capability_classes
        if missing:
            raise ValueError(
                f"RuntimeCapabilityPolicy must deny {sorted(missing)} explicitly."
            )

        # An id whose registry class is a write class cannot be allowed either —
        # otherwise the class deny-list could be sidestepped by naming the id.
        for cap_id in self.allowed_capability_ids:
            entry = SKILL_REGISTRY.get(cap_id)
            if entry is not None and entry.capability_class.value in ALWAYS_DENIED_CAPABILITY_CLASSES:
                raise ValueError(
                    f"RuntimeCapabilityPolicy allows capability {cap_id!r} whose class is "
                    f"{entry.capability_class.value} — write capabilities are never permitted."
                )
        return self

    # ── Queries ───────────────────────────────────────────────────────────────

    def permits_capability(self, capability_id: str, capability_class: str | None) -> bool:
        """True only if both the class and the id are explicitly permitted."""
        if capability_class is not None:
            if capability_class in self.denied_capability_classes:
                return False
            if capability_class not in self.allowed_capability_classes:
                return False
        return capability_id in self.allowed_capability_ids

    def permits_subagent(self, agent_id: str) -> bool:
        return agent_id in self.allowed_subagents

    def is_narrower_or_equal_to(self, other: "RuntimeCapabilityPolicy") -> bool:
        """
        True if this policy grants no authority ``other`` does not already grant.

        The privilege-expansion check. Applied across a procedure's whole
        lifecycle — after a retry, after a loop iteration, after a governance
        pause, after a restart — the answer must stay True at every point.
        """
        return (
            self.allowed_capability_ids <= other.allowed_capability_ids
            and self.allowed_capability_classes <= other.allowed_capability_classes
            and self.allowed_subagents <= other.allowed_subagents
            and self.denied_capability_classes >= other.denied_capability_classes
        )

    def assert_not_broadened(self, baseline: "RuntimeCapabilityPolicy") -> None:
        """Raise ``CapabilityDeniedError`` if this policy grew relative to ``baseline``."""
        if self.is_narrower_or_equal_to(baseline):
            return
        gained_ids = sorted(self.allowed_capability_ids - baseline.allowed_capability_ids)
        gained_classes = sorted(
            self.allowed_capability_classes - baseline.allowed_capability_classes
        )
        gained_subagents = sorted(self.allowed_subagents - baseline.allowed_subagents)
        raise CapabilityDeniedError(
            capability_id=",".join(gained_ids) or "-",
            capability_class=",".join(gained_classes) or None,
            policy_id=self.policy_id,
            reason=(
                "policy broadened relative to baseline "
                f"{baseline.policy_id}: capabilities={gained_ids} "
                f"classes={gained_classes} subagents={gained_subagents}"
            ),
        )


# ── Construction ──────────────────────────────────────────────────────────────

def build_capability_policy(
    *,
    definition: AgentDefinition,
    sop: SOPDefinition,
    agent_task_id: str,
    runtime: str,
    policy_revision: int = 1,
) -> RuntimeCapabilityPolicy:
    """
    Derive a policy from MAIW-controlled inputs only.

    Inputs, exhaustively:
        AgentDefinition.allowed_capabilities   what the agent may ever invoke
        SOPDefinition.allowed_capabilities     what this procedure narrows that to
        AgentDefinition.allowed_subagents      who the agent may delegate to
        SOPDefinition.allowed_subagents        who this procedure narrows that to
        SKILL_REGISTRY                         each capability's class
        GovernanceBoundary.allowed_capability_classes
        runtime                                which executor is being authorised

    Not inputs, ever: model output, a system or user prompt, an environment
    variable, a request header, or anything the sandbox says about itself. If a
    future caller wants to widen a policy, it edits an AgentDefinition or a SOP
    and that change goes through review — which is the point.

    The capability set is the *intersection* of the agent's and the SOP's
    allow-lists. A SOP naming something the agent does not have does not grant
    it; the narrower of the two always wins.
    """
    agent_caps = set(definition.allowed_capabilities)
    sop_caps = set(sop.allowed_capabilities)
    effective_caps = agent_caps & sop_caps if sop_caps else set()

    # Class allow-list: the agent's governance boundary, minus anything on the
    # permanent deny-list, and never anything outside the invocable classes.
    boundary_classes = set(definition.governance_boundary.allowed_capability_classes)
    allowed_classes = (
        boundary_classes & _INVOCABLE_CAPABILITY_CLASSES
    ) - ALWAYS_DENIED_CAPABILITY_CLASSES

    # Drop any capability whose registry class is not permitted. An unregistered
    # capability is dropped too: a policy must not vouch for something whose
    # class MAIW cannot determine.
    permitted_ids: set[str] = set()
    for cap_id in effective_caps:
        entry = SKILL_REGISTRY.get(cap_id)
        if entry is None:
            logger.warning(
                "build_capability_policy: dropping unregistered capability %r "
                "(agent=%s sop=%s) — class cannot be determined",
                cap_id, definition.agent_id, sop.id,
            )
            continue
        cls = entry.capability_class.value
        if cls in ALWAYS_DENIED_CAPABILITY_CLASSES:
            logger.warning(
                "build_capability_policy: refusing write capability %r (class=%s)",
                cap_id, cls,
            )
            continue
        if cls not in allowed_classes:
            logger.warning(
                "build_capability_policy: dropping capability %r — class %s not "
                "permitted by agent %s governance boundary",
                cap_id, cls, definition.agent_id,
            )
            continue
        permitted_ids.add(cap_id)

    agent_subagents = set(definition.allowed_subagents)
    sop_subagents = set(sop.allowed_subagents)
    effective_subagents = agent_subagents & sop_subagents if sop_subagents else set()

    policy = RuntimeCapabilityPolicy(
        policy_revision=policy_revision,
        agent_task_id=agent_task_id,
        sop_id=sop.id,
        sop_version=sop.version,
        runtime=runtime,
        allowed_capability_ids=frozenset(permitted_ids),
        allowed_capability_classes=frozenset(allowed_classes),
        denied_capability_classes=ALWAYS_DENIED_CAPABILITY_CLASSES,
        allowed_subagents=frozenset(effective_subagents),
    )
    logger.info(
        "RuntimeCapabilityPolicy issued: policy=%s agent=%s sop=%s/%s runtime=%s "
        "capabilities=%d subagents=%d",
        policy.policy_id, definition.agent_id, sop.id, sop.version, runtime,
        len(policy.allowed_capability_ids), len(policy.allowed_subagents),
    )
    return policy


# ── Enforcement seam ──────────────────────────────────────────────────────────

async def authorize_capability(
    policy: RuntimeCapabilityPolicy,
    capability_id: str,
    capability_class: str | None = None,
) -> None:
    """
    Deny-by-default gate, called immediately before a capability is invoked.

    Placed at the invocation point rather than at load time on purpose. A
    load-time check proves a SOP was well-formed when it was read; it proves
    nothing about what a runtime does three steps later. This is the seam a
    sandboxed executor must cross, so it is the seam that has to hold.

    Raises ``CapabilityDeniedError``. Never returns a boolean — a caller that
    forgets to check a boolean silently gains authority, whereas a caller that
    forgets to catch an exception fails closed.
    """
    resolved_class = capability_class
    if resolved_class is None:
        entry = SKILL_REGISTRY.get(capability_id)
        resolved_class = entry.capability_class.value if entry is not None else None

    if resolved_class is not None and resolved_class in policy.denied_capability_classes:
        logger.warning(
            "CAPABILITY DENIED (class): capability=%s class=%s policy=%s task=%s",
            capability_id, resolved_class, policy.policy_id, policy.agent_task_id,
        )
        raise CapabilityDeniedError(
            capability_id=capability_id,
            capability_class=resolved_class,
            policy_id=policy.policy_id,
            reason=f"capability class {resolved_class} is permanently denied",
        )

    if resolved_class is None:
        # Unknown class means MAIW cannot prove the capability is safe. Deny.
        logger.warning(
            "CAPABILITY DENIED (unknown class): capability=%s policy=%s",
            capability_id, policy.policy_id,
        )
        raise CapabilityDeniedError(
            capability_id=capability_id,
            capability_class=None,
            policy_id=policy.policy_id,
            reason="capability is not in the MAIW skill registry; class cannot be verified",
        )

    if resolved_class not in policy.allowed_capability_classes:
        raise CapabilityDeniedError(
            capability_id=capability_id,
            capability_class=resolved_class,
            policy_id=policy.policy_id,
            reason=f"capability class {resolved_class} is not permitted by this policy",
        )

    if capability_id not in policy.allowed_capability_ids:
        logger.warning(
            "CAPABILITY DENIED (not declared): capability=%s policy=%s task=%s",
            capability_id, policy.policy_id, policy.agent_task_id,
        )
        raise CapabilityDeniedError(
            capability_id=capability_id,
            capability_class=resolved_class,
            policy_id=policy.policy_id,
            reason="capability is not on this policy's allow-list",
        )


async def authorize_subagent(policy: RuntimeCapabilityPolicy, agent_id: str) -> None:
    """Deny-by-default gate for delegation. Same contract as ``authorize_capability``."""
    if not policy.permits_subagent(agent_id):
        logger.warning(
            "SUBAGENT DENIED: agent=%s policy=%s task=%s",
            agent_id, policy.policy_id, policy.agent_task_id,
        )
        raise CapabilityDeniedError(
            capability_id=f"subagent:{agent_id}",
            capability_class="SUBAGENT",
            policy_id=policy.policy_id,
            reason="subagent is not on this policy's allow-list",
        )


async def authorize_step(policy: RuntimeCapabilityPolicy, step: object) -> None:
    """
    Authorize everything one SOP step is about to touch.

    Both runtimes call exactly this function, which is the point: section 17 of
    the hardening spec requires that no capability logic can drift between the
    deterministic and adaptive runtimes. There is one implementation, so there
    is nothing to drift.

    Three surfaces are checked:
        step.skill_id                          a capability the step invokes
        step.completion.required_capability_result
                                               a capability whose result the
                                               step consumes — consuming a
                                               result is using the capability
        step.delegate_to                       a subagent the step delegates to

    ``step`` is typed loosely to keep this module free of a circular import back
    to ``contracts.sop``; it is always a ``SOPStep``.
    """
    skill_id = getattr(step, "skill_id", None)
    if skill_id:
        await authorize_capability(policy, skill_id)

    completion = getattr(step, "completion", None)
    required_result = getattr(completion, "required_capability_result", None) if completion else None
    if required_result:
        await authorize_capability(policy, required_result)

    delegate_to = getattr(step, "delegate_to", None)
    if delegate_to:
        await authorize_subagent(policy, delegate_to)


__all__ = [
    "ALWAYS_DENIED_CAPABILITY_CLASSES",
    "CapabilityDeniedError",
    "RuntimeCapabilityPolicy",
    "build_capability_policy",
    "authorize_capability",
    "authorize_subagent",
    "authorize_step",
]
