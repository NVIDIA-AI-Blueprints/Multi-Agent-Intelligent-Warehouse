# Phase 19A.11 — Runtime Component Ownership Matrix

**Phase:** 19A.11 (Runtime Simplification Audit)
**Date:** 2026-09-19
**Branch:** feat/phase-19a-deep-agents-poc
**Status:** COMPLETE

---

## Ownership Classification Table

| Component | File/Class | LOC | Warehouse-specific? | Generic runtime? | Deep Agents equiv | Verdict |
|---|---|---|---|---|---|---|
| AgentRuntime Protocol | contracts/runtime.py | 125 | Yes | Seam | Protocol | KEEP MAIW |
| AgentDefinition | contracts/agent.py | 204 | Yes | No | AgentDefinition | KEEP MAIW |
| AgentTaskState | contracts/task.py | 280 | Yes | Partially | DeepAgentState | KEEP MAIW (authoritative) |
| SOPDefinition | contracts/sop.py | 338 | Yes | No | system_prompt | KEEP MAIW |
| SKILL_REGISTRY | contracts/registry.py | 334 | Yes | No | None | KEEP MAIW |
| MAIWDeterministicRuntime | runtime/deterministic.py | 364 | Partially | Yes | create_deep_agent | KEEP as reference |
| DeepAgentsRuntime | runtime/deep_agents_runtime.py | ~577 | Adapter only | Adapter | real SDK | KEEP (adapter) |
| _SimulatedDeepAgentsRuntime | runtime/deep_agents_runtime.py | ~657 | No | Yes | real SDK | REMOVED (19A.11b) |
| MAIWModelGatewayChat | runtime/model_adapter.py | ~150 | Yes | Adapter | BaseChatModel | KEEP (adapter) |
| MAIWTestModelAdapter | runtime/model_adapter.py | ~180 | No | Test util | — | RENAMED (was MAIWModelAdapter) |
| MAIWSkillAdapter | runtime/skill_adapter.py | ~335 | Yes | Adapter | StructuredTool | KEEP |
| _build_maiw_tools() | runtime/deep_agents_runtime.py | ~40 | Yes | Adapter | StructuredTool | KEEP |
| _build_subagent_specs() | runtime/deep_agents_runtime.py | ~60 | Yes | Adapter | SubAgent | KEEP |
| check_capability_alignment | contracts/runtime.py | ~30 | Yes | Guard | — | CONSOLIDATED |

---

## Duplicate Orchestration Analysis

The `_SimulatedDeepAgentsRuntime` (removed in 19A.11b) duplicated:

| Duplicated concern | LOC | Who now owns it |
|---|---|---|
| Planning loop (plan generation, step sequencing) | ~60 | Deep Agents (LangGraph loop) |
| Step dispatch (action-type routing) | ~80 | Deep Agents (tool dispatch) |
| Subagent delegation logic (request/response cycle) | ~80 | Deep Agents (SubAgent scheduling) |
| Working context scratchpad (intermediate state) | ~40 | Deep Agents (LangGraph state) |
| Error/exception handling loop | ~40 | Deep Agents (internal graph error handling) |
| **Total removed** | **~300** | **deep_agents==0.7.15 SDK** |

Additional helpers removed (only used by `_SimulatedDeepAgentsRuntime`):
- `_infer_delegate_target()` — ~13 LOC
- `_build_step_prompt()` — ~19 LOC
- `_extract_step_results()` — ~83 LOC

**Total LOC removed from deep_agents_runtime.py: ~657**

---

## SOP Ownership vs Orchestration — Canonical Principle

> **"SOP = procedural policy / operating envelope. Deep Agents = adaptive runtime inside the envelope."**

MAIW SOPs define:
- Allowed phases and step sequence
- Mandatory governance handoff (`emit_recommended_action` → `WAITING_FOR_GOVERNANCE`)
- Allowed skill classes (`allowed_capabilities`)
- Allowed specialist agents (`allowed_subagents`)
- Termination rules (`stop_conditions`)
- Objective and policy boundaries

Deep Agents decides (within the SOP envelope):
- WHICH read skill to call at each step
- WHEN to call a subagent vs. reason directly
- HOW to decompose a step into sub-questions
- HOW to manage intermediate context between steps

MAIW does not implement a general-purpose agent framework. It defines warehouse-specific
operational semantics and contracts. Generic adaptive execution is delegated to the runtime.

---

## Deterministic Runtime Role Assessment

| Role | Applies? | Justification |
|---|---|---|
| A. Production runtime (strict SOP compliance) | YES | Safety-sensitive workflows needing exact SOP order, no LLM nondeterminism |
| B. Test/reference runtime | YES | Deterministic baseline for architecture tests and SOP conformance |
| C. Fallback runtime | YES | Degraded-mode operation when model/framework unavailable |
| D. Redundant (should be removed) | NO | Serves distinct use cases from DeepAgentsRuntime |

`MAIWDeterministicRuntime` is NOT redundant. It serves orthogonal purposes.

---

## Workload Suitability Matrix

| Workflow type | Preferred runtime | Reason |
|---|---|---|
| Fixed approval flows | deterministic | Exact SOP order, reproducible |
| Safety procedural checks | deterministic | No LLM nondeterminism |
| Complex root-cause investigation | deep_agents | Adaptive reasoning, dynamic tool selection |
| Cross-domain exception analysis | deep_agents | Multi-step with specialist delegation |
| CI/CD test pipeline | deterministic | Reproducible, no model dependency |
| Production adaptive reasoning | deep_agents | With ModelGateway + human approval |

---

## Runtime Selection Policy

Runtime selection belongs in `SOPDefinition` as an optional field `runtime_profile`:

```python
runtime_profile: Literal["strict", "adaptive"] = Field(
    default="strict",
    description=(
        "'strict' → MAIWDeterministicRuntime (default, production-safe). "
        "'adaptive' → DeepAgentsRuntime (LLM-adaptive, specialist delegation). "
        "Used by get_runtime() when no explicit override is provided."
    ),
)
```

Selection priority (highest to lowest):
1. Explicit `config` argument to `get_runtime()`
2. `MAIW_AGENT_RUNTIME` environment variable
3. `sop.runtime_profile` field
4. Default: `"deterministic"`

This is simple, explicit, and co-located with the SOP contract.

---

## Code Size Before/After

| File | LOC before | LOC after | Change |
|---|---|---|---|
| deep_agents_runtime.py | 1234 | ~577 | -657 (removed `_SimulatedDeepAgentsRuntime` + helpers) |
| model_adapter.py | 421 | ~425 | +4 (alias + docstring update) |
| runtime/__init__.py | 29 | ~39 | +10 (updated exports) |
| contracts/runtime.py | 125 | ~160 | +35 (added `check_capability_alignment`) |
| contracts/sop.py | 338 | ~350 | +12 (added `runtime_profile` field) |
| **Total runtime LOC** | **~2383** | **~1750** | **-633** |
