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

---

## File Map

| File | Responsibility |
|---|---|
| `contracts/runtime.py` | AgentRuntime Protocol, AgentExecutionContext, AgentTaskResult, check_capability_alignment |
| `contracts/sop.py` | SOPDefinition (runtime_profile field), SOPStep, StepCondition, validate_sop |
| `contracts/agent.py` | AgentDefinition, TerminationPolicy, GovernanceBoundary |
| `contracts/task.py` | AgentTaskState, AgentTaskStatus, valid transition map |
| `contracts/registry.py` | SKILL_REGISTRY, CapabilityClass |
| `runtime/deep_agents_runtime.py` | DeepAgentsRuntime, get_runtime, _build_maiw_tools, _build_subagent_specs, _build_sop_system_prompt |
| `runtime/deterministic.py` | MAIWDeterministicRuntime |
| `runtime/model_adapter.py` | MAIWModelGatewayChat (production), MAIWTestModelAdapter (test) |
| `runtime/skill_adapter.py` | MAIWSkillAdapter, MAIWAgentTool |
