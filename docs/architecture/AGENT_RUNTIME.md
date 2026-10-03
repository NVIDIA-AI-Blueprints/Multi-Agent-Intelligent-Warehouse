# MAIW Agent Runtime Architecture

**Version:** MAIW v2
**Status:** AUTHORITATIVE
**Diagram:** [docs/architecture/diagrams/maiw-runtime-pipeline.png](diagrams/maiw-runtime-pipeline.png)

---

## Three-Layer Ownership Model

```
MAIW owns:        operational semantics, SOPs, task state, permissions, governance
Deep Agents owns: adaptive runtime loop, tool/subagent scheduling, working context
MCP owns:         protocol / interoperability
```

---

## Core Principle

MAIW does not implement a general-purpose agent framework. MAIW defines
warehouse-specific agent contracts, SOPs, operational context, permissions,
governance and execution semantics. Generic adaptive agent execution is
provided by pluggable runtimes such as Deep Agents through the AgentRuntime interface.

---

## SOP = Policy Envelope. Deep Agents = Adaptive Runtime Inside the Envelope.

**SOPs define:**
- Allowed phases and step sequence (procedure)
- Mandatory governance handoff (`emit_recommended_action` → `WAITING_FOR_GOVERNANCE`)
- Allowed skill classes (`allowed_capabilities`) — READ/ANALYTICAL only
- Allowed specialist agents (`allowed_subagents`)
- Termination rules (`stop_conditions`)
- Objective and policy boundaries

**Deep Agents decides** (within SOP boundaries):
- WHICH read skill to call at each step
- WHEN to call a subagent vs. reason directly
- HOW to decompose a step into sub-questions
- HOW to manage intermediate context between steps

---

## Runtime Selection

```yaml
runtime_profile: strict    # → MAIWDeterministicRuntime (default)
runtime_profile: adaptive  # → DeepAgentsRuntime (LLM-adaptive)
```

Selection priority (highest wins):
1. Explicit `config` argument to `get_runtime(config=...)`
2. `MAIW_AGENT_RUNTIME` environment variable
3. `sop.runtime_profile` field in SOPDefinition
4. Default: `"deterministic"`

---

## Runtimes

### MAIWDeterministicRuntime (strict mode)

- **Purpose:** Exact SOP step execution, no LLM nondeterminism
- **Use for:** Fixed approval flows, safety-sensitive procedural checks, CI/CD pipelines, fallback/degraded mode
- **Dependencies:** None beyond MAIW packages
- **Key property:** Reproducible — same inputs always produce same output

### DeepAgentsRuntime (adaptive mode)

- **Purpose:** Adaptive reasoning within SOP envelope
- **Use for:** Complex root-cause investigation, cross-domain exception analysis, specialist delegation
- **Dependencies:** `deepagents==0.7.15` (LangChain/LangGraph)
- **Model:** `MAIWModelGatewayChat` → MAIW ModelGateway (hard invariant — no direct providers)
- **Key property:** Adaptive — selects tools and subagents dynamically within SOP bounds

#### MAIWModelGatewayChat — ModelGateway adapter contract

`DeepAgentsRuntime` passes `MAIWModelGatewayChat(model_gateway=context.model_gateway)` to
`create_deep_agent()`. All model calls flow through this chain:

```
DeepAgentsRuntime
  → MAIWModelGatewayChat._generate() / _agenerate()
      → ModelRequest(task, messages, reasoning, risk_level, trace_id, ...)
      → context.model_gateway.generate(request)   # canonical contract
          → ModelResponse
      → ModelResponse.content → AIMessage.content → ChatResult
```

**Invariants:**

1. `MAIWModelGatewayChat` constructs a `ModelRequest` object; it NEVER passes bare
   `prompt=`, `risk_level=`, or `reasoning_level=` kwargs directly to `gateway.generate()`.
2. `ModelResponse.content` is translated directly to `AIMessage.content` — no re-wrapping.
3. Gateway failures (any exception from `gateway.generate()`) propagate to the caller.
   They are NOT converted into mock or placeholder responses.
4. Mock responses are returned ONLY when `model_gateway=None` (explicit test mode,
   set by the caller). This must never be activated by exception handling.

**Test mode vs. production:**

| `model_gateway` | Behavior |
|----------------|----------|
| `None` | Explicit test mode — returns deterministic `_mock_response()` without network calls |
| a `ModelGateway` instance | Production mode — constructs `ModelRequest`, calls `generate(request)`, propagates exceptions |

Tests that need isolation must pass `model_gateway=None` explicitly. Production code
must never set `model_gateway=None` unless it is intentionally running deterministic
test fixtures.

---

## Authority Boundary

```
Agent (either runtime)
    → RecommendedAction
    → WAITING_FOR_GOVERNANCE
──────── MAIW AUTHORITY BOUNDARY ────────
DecisionEngine
    → Human Approval
    → ActionExecutor
    → MCP
    → Operational System
```

No runtime may cross this boundary. Enforced structurally:
- `AgentRuntime.run_task()` cannot return `COMPLETED` while bypassing governance
- `emit_recommended_action` step always transitions to `WAITING_FOR_GOVERNANCE`
- `_build_maiw_tools()` hard-blocks WRITE/EMERGENCY_WRITE skills from agent tool list
- `check_capability_alignment()` rejects SOPs with WRITE capabilities at invocation time

---

## Shared Guard: check_capability_alignment

Extracted from both runtimes into `contracts/runtime.py` as a standalone function.

```python
from maiw_agents.contracts.runtime import check_capability_alignment

check_capability_alignment(definition, sop)
# Raises ValueError if:
# - SOP capabilities are not a subset of definition capabilities
# - SOP contains WRITE or EMERGENCY_WRITE capabilities
```

This is a MAIW-owned guard, not a runtime-specific concern. Both runtimes
delegate to it before graph/step invocation.

---

## RuntimeCapabilityPolicy — the runtime receives a bounded grant it cannot expand

`check_capability_alignment` above is a **load-time** check: it proves a SOP was
well-formed when it was read. It says nothing about what a runtime does three
steps later. `RuntimeCapabilityPolicy` is the complementary **runtime** contract.

```python
from maiw_agents.contracts.capability_policy import (
    build_capability_policy, authorize_step,
)

policy = build_capability_policy(
    definition=definition, sop=sop,
    agent_task_id=state.task_id, runtime=self.RUNTIME_NAME,
)
...
await authorize_step(policy, step)   # raises CapabilityDeniedError
```

**The runtime does not construct its own authority and cannot widen what it is
given.** The policy is a frozen model with frozenset members, derived only from
the `AgentDefinition`, the `SOPDefinition` and the capability registry — never
from model output, a prompt, an environment variable, or anything a sandbox
declares about itself. The capability set is the *intersection* of the agent's
and the SOP's allow-lists, so a SOP naming something the agent lacks does not
grant it.

Deny-by-default: a capability absent from the allow-list is denied, including
one that did not exist when the policy was issued, and one the registry cannot
classify. `WRITE` and `EMERGENCY_WRITE` are denied unconditionally in every
policy that can be constructed.

Both runtimes call the same `authorize_step`, so there is no second
implementation to drift:

| Runtime | How the policy is applied |
|---|---|
| `MAIWDeterministicRuntime` | `authorize_step` before each step is fulfilled; a denial returns `ESCALATED` with `CAPABILITY_DENIED`. |
| `DeepAgentsRuntime` | The tool set handed to the model is *derived from the policy* (`_build_maiw_tools(..., policy)`), **and** `authorize_step` runs before the graph is invoked for each step. The filtered tool list is a construction-time restriction; the runtime check holds even if the graph is rebuilt or a tool leaks in. |

A policy cannot broaden across retry, loop, governance pause or restart —
policies are derived rather than stored, so a restored procedure rebuilds the
identical grant set from the same reviewed inputs.
`assert_not_broadened(baseline)` is the assertion, exercised end-to-end in
`test_runtime_capability_policy.py`.

This is the contract a sandboxed executor is handed instead of being trusted to
restrain itself within a wider surface. Phase 20A took delivery of it — see
below.

---

## Sandbox Execution Context (Phase 20A contracts, Phase 20B security boundary qualified)

Either runtime can run inside a sandbox boundary. The boundary is a decorator,
not a port:

```python
runtime = SandboxedAgentRuntime(
    inner=MAIWDeterministicRuntime(...),   # or DeepAgentsRuntime
    config=SandboxConfig.from_env(),
    provisioner=OpenShellSandboxProvisioner(),
)
```

`SandboxedAgentRuntime` implements the `AgentRuntime` Protocol structurally and
adds exactly three things around the wrapped runtime:

1. render the `RuntimeCapabilityPolicy` into a sandbox policy
2. obtain a sandbox and apply that policy — or fail closed
3. delegate to the wrapped runtime

It reimplements no step sequencing, no capability check and no governance
transition. **The wrapped runtime is unaware it is sandboxed.** That is the
containment property stated as a code fact: deleting
`integrations/nemoclaw/` would leave capability enforcement, governance handoff
and procedure persistence exactly as they are, and remove only the second wall.

Order matters and is not an implementation detail. The policy is built and
rendered *before* the sandbox is consulted, so a policy that cannot be rendered
safely fails the task without anything having been started. The sandbox is then
asked to enforce a policy that already exists, rather than asked what it is
willing to enforce.

| Mode | Sandbox unavailable |
|---|---|
| `DISABLED` | delegate directly; no policy rendered |
| `SANDBOX_REQUIRED` | **raise.** No path reaches the inner runtime |
| `SANDBOX_PREFERRED` | warn and continue; `RuntimeCapabilityPolicy` still applies |

A sandbox that starts but cannot apply its policy is treated as *unavailable*,
not as partially contained — an uncontained process that happens to be in a
container is worse than no sandbox, because it looks contained in the logs.

**What the sandbox does not do:** authorise anything. Every `authorize_step`
call that runs unsandboxed still runs sandboxed, in the same place. A deployment
that treated the sandbox as the control and relaxed the policy would have fewer
walls, not more.

Inference is unchanged in authority: `MAIWModelGatewayChat` reaches a host-side
MAIW endpoint fronting `ModelGateway`. The sandbox holds no provider key and
selects no model. NemoClaw's Model Router is explicitly not adopted
(`use_platform_model_router: false` in the manifest) — it would bypass
`PolicyFilter`, `DeploymentResolver` and routing provenance in one step.

See [NEMOCLAW_OPENSHELL_INTEGRATION.md](NEMOCLAW_OPENSHELL_INTEGRATION.md) for
the ownership matrix, threat model, and current qualification status.

---

## Long-Term Direction

Deep Agents is the primary adaptive runtime. MAIWDeterministicRuntime remains
as the reference executor and strict-mode fallback. The dual-runtime period is
for validation, not an end state.

As confidence in Deep Agents integration grows:
1. `runtime_profile: adaptive` becomes default for complex resolution SOPs
2. `runtime_profile: strict` retained for safety-critical procedural SOPs
3. `MAIWDeterministicRuntime` retained permanently as reference and strict fallback

**The dual-runtime architecture is an intentional design, not technical debt.**
It provides a clean separation between deterministic compliance and adaptive reasoning.

The decision to retain Deep Agents as an optional adaptive runtime was validated through the Phase 19A runtime comparison. See [`artifacts/phase19a/runtime_comparison_real_deepagents.json`](../../artifacts/phase19a/runtime_comparison_real_deepagents.json) for the preserved evaluation artifact (`adoption_decision`: "KEEP DEEP AGENTS AS OPTIONAL RUNTIME"). The architecture document above remains normative — the artifact is evidence, not specification.

---

## File Map

| File | Responsibility |
|---|---|
| `contracts/runtime.py` | AgentRuntime Protocol, AgentExecutionContext, AgentTaskResult, check_capability_alignment |
| `contracts/sop.py` | SOPDefinition (runtime_profile field), SOPStep, StepCondition, validate_sop |
| `contracts/agent.py` | AgentDefinition, TerminationPolicy, GovernanceBoundary |
| `contracts/task.py` | AgentTaskState, AgentTaskStatus, valid transition map |
| `contracts/registry.py` | SKILL_REGISTRY, CapabilityClass |
| `contracts/capability_policy.py` | RuntimeCapabilityPolicy, build_capability_policy, authorize_capability / authorize_subagent / authorize_step, CapabilityDeniedError |
| `contracts/procedure_state.py` | ProcedureExecutionState (incl. `revision`), ProcedureStatus |
| `sop_engine/state_store.py` | ProcedureStateStore, InMemoryProcedureStateStore, JsonFileProcedureStateStore |
| `runtime/deep_agents_runtime.py` | DeepAgentsRuntime, get_runtime, _build_maiw_tools, _build_subagent_specs, _build_sop_system_prompt |
| `runtime/deterministic.py` | MAIWDeterministicRuntime |
| `runtime/model_adapter.py` | MAIWModelGatewayChat (production), MAIWTestModelAdapter (test) |
| `runtime/skill_adapter.py` | MAIWSkillAdapter, MAIWAgentTool |
