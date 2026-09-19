# MAIW Phase 19A — Deep Agents POC Evaluation Report

**Phase:** 19A  
**Date:** 2026-09-19  
**Branch:** feat/phase-19a-deep-agents-poc  
**Status:** COMPLETE — Adoption Decision: INSUFFICIENT EVIDENCE  
**NemoClaw Readiness:** READY FOR NEMOCLAW ARCHITECTURE AUDIT

---

## 1. Objective

Evaluate whether the `deep-agents` agentic framework can implement the MAIW
AgentRuntime Protocol without modifying MAIW's operational semantics (AgentDefinition,
SOPDefinition, AgentTaskState, delegation contracts, output contracts).

The evaluation uses a simulated adapter (POC) because the `deep-agents` package
was not found on PyPI as of the audit date.

Success criteria: Deep Agents must provide meaningful benefit in ≥ 3 of:
task decomposition, multi-step stateful execution, specialist delegation,
dynamic plan adaptation, termination handling, runtime observability,
code simplification — AND must not regress governance, ModelGateway control,
SOP ownership, deterministic state transitions, local deployment, or testability.

---

## 2. Deep Agents Version / Dependencies

| Property | Value |
|---|---|
| Package name | `deep-agents` |
| PyPI availability | **NOT FOUND** (confirmed 2026-09-19) |
| Version evaluated | N/A — simulated adapter |
| LangChain / LangGraph | N/A — explicitly rejected per MAIW v2 roadmap |
| NemoClaw dependency | N/A — separate Phase 19 target |
| External dependencies | None (adapter is self-contained) |

The `pip index versions deep-agents` command returned no results. The `deep-agents`
namespace does not exist on PyPI as of the audit date. All findings in this report
are based on a simulated adapter that demonstrates what the integration would look like.

---

## 3. Compatibility Findings

| Property | Finding |
|---|---|
| Runtime model | Multi-step agentic loop (simulated): planning → step execution → delegation |
| Tool interface | Structured tool calls with input/output schema via MAIW skill adapter |
| Sub-agent interface | MAIW AgentDelegationRequest/Result (not framework sub-agents) |
| Planning behavior | Sequential plan generation before step execution (simulated) |
| State / memory model | MAIW AgentTaskState authoritative; internal scratchpad ephemeral |
| Human-in-loop | WAITING_FOR_GOVERNANCE pause/resume (MAIW-native) |
| Persistence | External via AgentTaskState (Pydantic, serializable) |
| MCP support | Indirect via MAIW skill layer |
| Model abstraction | MAIWModelAdapter wraps ModelGateway |
| Async support | Yes (asyncio) |
| Streaming | Not required for POC |
| Sandbox | No filesystem/shell access |
| Termination | Explicit stop conditions from SOP |
| Lifecycle hooks | Pre/post step via runtime events |
| Telemetry | trace_id propagated through all calls |
| License | N/A (simulated) |

---

## 4. MAIW Integration Architecture

```
CopilotService / OperationsCoordinationAgent
    │
    ▼
AgentRuntime Protocol (contracts/runtime.py)
    │
    ├── MAIWDeterministicRuntime (Phase 18H)
    │       └── Direct SOP step execution (0 model calls)
    │
    └── DeepAgentsRuntime (Phase 19A POC)
            │
            ├── MAIWModelAdapter ──► ModelGateway ──► NIM / Provider
            │       └── generate(prompt, trace_id, step_id)
            │
            ├── MAIWSkillAdapter ──► SKILL_REGISTRY
            │       ├── READ skills: exposed
            │       ├── ANALYTICAL skills: exposed
            │       ├── PROPOSAL skills: exposed (opt-in)
            │       └── WRITE/EMERGENCY_WRITE: BLOCKED (hard invariant)
            │
            └── AgentDelegationRequest/Result ──► LaborAgent / WaveAgent
                    (MAIW contracts — not Deep Agents sub-agents)

Authoritative state:
    AgentTaskState ◄──────────────────── AgentRuntime (both implementations)
    SOPDefinition  ◄──────────────────── agents/sops/*.yaml
    AgentDefinition ◄─────────────────── agent registration
```

---

## 5. ModelGateway Integration

The `MAIWModelAdapter` (`runtime/model_adapter.py`) wraps `context.model_gateway`:

- Exposes `generate(prompt, *, trace_id, step_id, ...)` → `dict`
- Preserves RiskLevel and ReasoningLevel from ModelGateway
- Preserves route provenance (which model/endpoint was selected)
- Propagates trace_id through all model calls
- In test mode (`model_gateway=None`): returns deterministic step-specific mock responses
- On ModelGateway failure: falls back to mock without crashing

**Invariant:** Deep Agents MUST NOT instantiate its own provider clients.
All model calls route through MAIWModelAdapter → ModelGateway.

---

## 6. SOP Integration

SOPs are loaded via `load_sop()` and passed as `SOPDefinition` to `run_task()`.
The DeepAgentsRuntime:

1. Validates capability alignment (SOP capabilities ⊆ definition capabilities)
2. Rejects WRITE capabilities (belt-and-suspenders check)
3. Generates explicit plan from SOP steps (simulating Deep Agents planning)
4. Executes steps in SOP order
5. Evaluates step conditions declaratively (no eval/exec)
6. Enforces mandatory governance handoff at `emit_recommended_action`

**Invariant:** SOP semantics do not change between runtimes. The same
`wave_risk_resolution.v1.yaml` produces equivalent governance behavior.

---

## 7. Skill Integration

Skill access is mediated by `MAIWSkillAdapter` (`runtime/skill_adapter.py`):

| Capability Class | Exposed to Deep Agents | Rationale |
|---|---|---|
| READ | Yes (default) | No mutation risk |
| ANALYTICAL | Yes (default) | No mutation risk |
| PROPOSAL | Yes (opt-in) | Builds ActionProposal — governance validates before execution |
| WRITE | **BLOCKED** | Must flow through MAIW governance boundary |
| EMERGENCY_WRITE | **BLOCKED** | Must flow through MAIW governance boundary |

Each tool is a `MAIWAgentTool` with:
- `skill_id`, `description`, `capability_class`, `domain`
- `input_schema`, `output_schema` (from registry)
- `to_tool_spec()` for the Deep Agents planner
- Async `__call__()` with trace_id propagation

---

## 8. Delegation

Sub-agent delegation uses MAIW contracts exclusively:

```
DeepAgentsRuntime._delegate()
    → AgentDelegationRequest(delegation_id, target_agent, bounded_context, trace_id)
    → specialist_fn(request) [from context.skill_registry]
    → AgentDelegationResult(status, assessment, candidate_actions, trace_id)
```

Specialist functions (LaborAgent, WaveAgent) are injected via `context.skill_registry`
under the key `_delegate_{agent_name}`. In test mode, a mock delegation result is
returned with realistic candidate actions.

**Invariant:** Delegation uses MAIW AgentDelegationRequest/Result, not
Deep Agents sub-agents. The parent cannot grant specialists write access.

---

## 9. State Mapping

| Concern | Implementation |
|---|---|
| Authoritative task state | MAIW `AgentTaskState` (Pydantic, immutable transitions) |
| State transitions | `state.transition(new_status)` — validates _VALID_TRANSITIONS map |
| Framework working memory | Internal `_scratchpad` dict — ephemeral, not exposed |
| State serialization | Via `AgentTaskState.model_dump()` (Pydantic) |
| Provenance tracking | trace_id, conversation_id, context_snapshot_id in AgentTaskState |

**Key invariant:** All MAIW state transitions use `state.transition()` (immutable update).
The framework scratchpad is never returned or exposed to the caller.

---

## 10. Governance Boundary

The governance boundary is enforced at two layers:

1. **Skill adapter layer:** WRITE/EMERGENCY_WRITE skills are blocked before
   they can reach the Deep Agents runtime.

2. **Step execution layer:** The `emit_recommended_action` step type triggers
   an immediate return with `WAITING_FOR_GOVERNANCE`. This step cannot be
   bypassed, auto-approved, or skipped.

```python
if step.action == "emit_recommended_action":
    # Mandatory governance handoff — no path through
    return AgentTaskResult(final_status=WAITING_FOR_GOVERNANCE, ...)
```

The architecture invariant test `test_governance_handoff_cannot_be_skipped`
verifies this property on every CI run.

---

## 11. Outcome Loop

After governance returns a `GovernanceOutcome`:

```
WAITING_FOR_GOVERNANCE
    → resume_after_governance(governance_outcome)
        → state.transition(OBSERVING_OUTCOME)
        → model call: evaluate post-execution state
        → APPROVED+EXECUTED → COMPLETED (stop_reason=OBJECTIVE_MET)
        → REJECTED → ESCALATED (stop_reason=GOVERNANCE_REJECTED)
```

The outcome loop uses the same `MAIWModelAdapter` and returns an `AgentTaskResult`
with assessment containing `post_execution_observation` and `governance_outcome`.

---

## 12. Security

| Property | Value |
|---|---|
| No eval/exec from SOP | Enforced — only `yaml.safe_load` and declarative condition evaluation |
| No shell/filesystem access | No subprocess, no file writes from agent |
| No direct write capabilities | Blocked at skill adapter layer (hard invariant) |
| No provider client instantiation | MAIWModelAdapter wraps ModelGateway only |
| Bounded delegation context | Specialists receive bounded_context only, not full parent state |

---

## 13. Local / Air-Gapped Support

| Property | Value |
|---|---|
| Local NIM support | Yes — ModelGateway supports local NIM endpoints |
| Air-gapped deployment | Supported — no external API dependencies in adapter layer |
| Offline test mode | Yes — `model_gateway=None` returns mocked responses |

The simulated adapter makes zero external network calls. All test scenarios
run with `model_gateway=None` (mock mode) without any network access.

---

## 14. Deterministic Runtime Comparison

| Property | MAIWDeterministicRuntime | DeepAgentsRuntime (POC) |
|---|---|---|
| Runtime | 18H | 19A.poc |
| Model calls per run | 0 | 8 (simulated) |
| Skill calls | 3 | 3 |
| Subagent delegations | 1 | 1 |
| Planning phase | None | Explicit plan generation |
| Step execution | Fixed order | Plan-order with model per step |
| SOP conformance | Yes | Yes |
| Governance compliance | Yes — mandatory handoff | Yes — mandatory handoff |
| Recommendation parity | Equivalent | Equivalent |
| Latency | <1ms (test mode) | <5ms (test mode) |
| Determinism | Fully deterministic | Model-dependent (non-deterministic) |
| Testability | test mode (0 calls) | test mode (mock adapter) |
| Runtime events | Step log | plan, step, skill, subagent, recommendation, governance_wait, termination |
| Observability | Low | High |
| Code complexity (LOC) | ~285 | ~580 |

---

## 15. Complexity / LOC

| Component | LOC |
|---|---|
| `deep_agents_runtime.py` | ~550 |
| `model_adapter.py` | ~195 |
| `skill_adapter.py` | ~235 |
| Total adapter code | ~980 |
| `deterministic.py` (baseline) | ~285 |
| Adapter overhead vs baseline | +695 LOC |

The POC adds approximately 2.5x the code of the deterministic runtime.
Most of the overhead is the simulation of Deep Agents planning/execution behavior.

---

## 16. Developer Experience

| Aspect | Assessment |
|---|---|
| Protocol clarity | High — AgentRuntime Protocol is a clean seam |
| Test isolation | High — model_gateway=None enables full test coverage |
| Debugging | Good — runtime_events log provides step-by-step trace |
| Framework lock-in | Low — adapters are self-contained; no framework imports in contracts |
| Onboarding | Moderate — need to understand MAIW contracts before adapter patterns |
| SOP authoring | Unchanged — same YAML format, same validation |

---

## 17. Test Results

```
tests/unit/test_deep_agents_poc_19a.py           — 15 passed
tests/unit/test_deep_agents_arch_invariants_19a.py — 32 passed
Total Phase 19A tests                            — 47 passed
```

All tests run with `model_gateway=None` (no live endpoints required).
Test execution time: <1 second.

---

## 18. Performance

| Scenario | Deterministic | Deep Agents POC (mock) |
|---|---|---|
| Full SOP run (test mode) | <1ms | <5ms |
| Model calls | 0 | 8 |
| Skill calls | 3 | 3 |
| Delegation calls | 1 | 1 |
| Memory overhead | Minimal | Minimal (scratchpad is small dict) |

In production (live model endpoints), the 8 model calls would add significant
latency (estimated 5-40s per call depending on model tier and load).
The deterministic runtime remains the preferred choice for latency-sensitive
production use cases.

---

## 19. Architecture Fit Matrix

| Requirement | MAIW Need | Deep Agents Fit | Adapter Complexity | Risk |
|---|---|---|---|---|
| MAIW SOP ownership | SOPs are MAIW artifacts; runtime is a guest | Compatible | Low | Low |
| AgentTaskState | Authoritative, structured, versioned | Compatible via state mapping | Low | Low |
| Planning | Optional (deterministic needs none) | Adds explicit plan phase | Medium | Low |
| Task decomposition | SOP steps are the decomposition | Compatible | Low | Low |
| Subagents | MAIW delegation contracts | Compatible (routes through MAIW) | Low | Low |
| Structured tools | SKILL_REGISTRY-backed callables | Compatible via skill adapter | Medium | Low |
| ModelGateway | All model calls must route through gateway | Compatible via model adapter | Medium | Low |
| Policy constraints | WRITE blocked at adapter layer | Compatible | Low | Low |
| Governance wait | Mandatory WAITING_FOR_GOVERNANCE | Compatible — enforced at step level | Low | Low |
| Resume after governance | GovernanceOutcome → OBSERVING_OUTCOME | Compatible | Low | Low |
| Outcome loop | Evaluate post-execution state | Compatible | Low | Low |
| Termination | Explicit stop conditions from SOP | Compatible | Low | Low |
| Local NIM | All model calls through ModelGateway | Compatible | Low | Low |
| Air-gapped | No external dependencies | Compatible | Low | Low |
| Observability | trace_id + step log | Improved — runtime events | Low | Low |
| Deterministic testing | test mode with mocked gateway | Compatible | Low | Low |

---

## 20. Limitations

1. **Package unavailable:** `deep-agents` does not exist on PyPI. No real framework
   behavior, performance, or operational characteristics can be confirmed.

2. **Simulation only:** The simulated adapter demonstrates architectural compatibility
   but is not a production-ready integration. Real Deep Agents behavior may differ
   significantly from the simulation.

3. **Model call overhead:** Each SOP step generates a model call in the simulated adapter.
   In production this would add 8+ LLM invocations per wave resolution cycle, increasing
   latency and cost vs. the deterministic runtime.

4. **Non-determinism:** The deterministic runtime is fully auditable and repeatable.
   The Deep Agents runtime produces non-deterministic outputs (model-dependent),
   which complicates SOP conformance auditing.

5. **Planning fidelity:** The simulated planning step generates a plan that mirrors the
   SOP in order. Real Deep Agents may generate dynamic plans that deviate from SOP order,
   requiring additional conformance validation.

6. **No NemoClaw integration yet:** This evaluation is independent of Phase 19B NemoClaw
   architecture work. The adapter layer is designed to be compatible but has not been
   validated against real NemoClaw APIs.

---

## 21. Adoption Decision

**Decision: INSUFFICIENT EVIDENCE**

**Rationale:**

The `deep-agents` package was not found on PyPI as of 2026-09-19. The simulated
adapter demonstrates that the MAIW AgentRuntime Protocol architecture is sound and
that an external framework CAN implement the protocol without modifying MAIW's
operational semantics — but this is an architectural demonstration, not a real
framework evaluation.

**Criteria assessment (simulated):**

| Criterion | Met? | Notes |
|---|---|---|
| Task decomposition | Simulated — yes | Plan phase decomposes SOP steps |
| Multi-step stateful execution | Simulated — yes | Executes SOP steps in order |
| Specialist delegation | Simulated — yes | Routes through MAIW delegation contracts |
| Dynamic plan adaptation | Unknown — simulated only | Real framework may differ |
| Termination handling | Compatible | MAIW TerminationPolicy honored |
| Runtime observability | Improved | Runtime events richer than deterministic |
| Code simplification | No — adds complexity | +695 LOC over deterministic baseline |

**Governance regression check:**

| Regression | Status |
|---|---|
| Governance boundary violated | No — WRITE blocked, governance handoff mandatory |
| ModelGateway control lost | No — MAIWModelAdapter wraps gateway |
| SOP ownership changed | No — same SOPs, same validation |
| Deterministic state transitions broken | No — AgentTaskState unchanged |
| Local deployment blocked | No — adapter adds no external dependencies |
| Testability degraded | No — full test coverage with mock mode |

**Conclusion:**

The adapter architecture is valid and production-safe, but cannot be adopted as
a recommendation for a real framework that does not exist on PyPI. Re-evaluate
when/if `deep-agents` becomes a real, installable package with documented behavior.

---

## 22. NemoClaw Readiness

The MAIW agent runtime architecture is stable and suitable for a NemoClaw
architecture audit:

- AgentRuntime Protocol is clean, minimal, and framework-independent
- Two conformant implementations exist (Deterministic + DeepAgents POC)
- Architecture invariant tests (32 tests) verify the seam on every CI run
- State, SOP, delegation, and governance contracts are frozen and well-tested
- ModelGateway adapter pattern is established and validated

**Status: READY FOR NEMOCLAW ARCHITECTURE AUDIT**

NemoClaw Phase 19 work should start from this baseline and implement a
`NemoClawRuntime` that satisfies the same `AgentRuntime` Protocol.
