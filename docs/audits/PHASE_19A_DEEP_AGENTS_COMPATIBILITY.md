# MAIW Phase 19A — Deep Agents Compatibility Audit

**Audit Date:** 2026-09-19  
**Auditor:** Phase 19A POC  
**Status:** SIMULATED ADAPTER (package not found on PyPI)

---

## 1. Package Identity

| Field | Value |
|---|---|
| Package name | `deep-agents` |
| PyPI availability | **NOT FOUND** (confirmed 2026-09-19 via `pip index versions deep-agents`) |
| Implementation | Simulated adapter for POC evaluation — demonstrates integration pattern |
| Python requirement | N/A (simulated) |
| License | N/A (simulated) |

---

## 2. Dependency Audit

| Dependency | Status | Notes |
|---|---|---|
| LangChain | NOT REQUIRED | Explicitly rejected per MAIW v2 roadmap |
| LangGraph | NOT REQUIRED | Explicitly rejected per MAIW v2 roadmap |
| NemoClaw | NOT USED | Phase 19 target; separate architecture audit planned |
| External agent frameworks | NONE | POC is self-contained |

---

## 3. Runtime Model

| Property | Value |
|---|---|
| Execution model | Multi-step agentic loop with planning, task decomposition, sub-agent calls |
| Planning behavior | Sequential plan generation then step execution |
| Task decomposition | SOP steps mapped to explicit plan entries before execution |
| Sub-agent interface | Delegation with bounded context |

---

## 4. Tool Interface

| Property | Value |
|---|---|
| Tool call format | Structured tool calls with input/output schema |
| Tool filtering | Only READ and ANALYTICAL skills exposed (not WRITE/EMERGENCY_WRITE/PROPOSAL) |
| Tool registration | Maps MAIW SKILL_REGISTRY entries to callable tool objects |

---

## 5. State / Memory Model

| Property | Value |
|---|---|
| Working memory | Internal scratchpad (dict) — ephemeral, not authoritative |
| Authoritative state | MAIW AgentTaskState — external, structured |
| State transitions | All MAIW state transitions use AgentTaskState.transition() |
| State ownership | MAIW owns state; framework is a guest |

---

## 6. Human-in-Loop Support

| Property | Value |
|---|---|
| Pause/resume | Yes — WAITING_FOR_GOVERNANCE is a pause point |
| Governance handoff | Mandatory — emit_recommended_action step is not skippable |
| Resume mechanism | GovernanceOutcome injection transitions to OBSERVING_OUTCOME |

---

## 7. Persistence / Checkpointing

| Property | Value |
|---|---|
| Checkpointing | External to framework (not framework-native) |
| State serialization | Via AgentTaskState (Pydantic, serializable) |

---

## 8. MCP Support

| Property | Value |
|---|---|
| MCP integration | Indirect — via MAIW skill layer |
| Direct MCP calls | PROHIBITED for agents — must flow through MAIW governance boundary |
| Write MCP calls | BLOCKED — not exposed to Deep Agents adapter |

---

## 9. Model Abstraction

| Property | Value |
|---|---|
| Model adapter | MAIWModelAdapter wraps context.model_gateway |
| Direct provider clients | PROHIBITED — Deep Agents must not instantiate its own provider clients |
| Route provenance | Preserved from ModelGateway (RiskLevel, ReasoningLevel, route) |
| Trace correlation | trace_id propagated through all model calls |

---

## 10. Async Support

| Property | Value |
|---|---|
| Async | Yes — all run_task() calls are async |
| Streaming | Not required for POC |

---

## 11. Sandbox Assumptions

| Property | Value |
|---|---|
| Filesystem access | No |
| Shell access | No |
| Network access | Via ModelGateway only (controlled) |

---

## 12. Termination Semantics

| Property | Value |
|---|---|
| Termination | Explicit stop conditions from SOP |
| Iteration limit | Enforced by TerminationPolicy.max_iterations |
| Stop reasons | OBJECTIVE_MET, NO_SAFE_ACTION, HUMAN_REQUIRED, MAX_ITERATIONS_REACHED |

---

## 13. Lifecycle Hooks

| Property | Value |
|---|---|
| Pre-step hook | Recorded in runtime events (plan entry) |
| Post-step hook | Recorded in runtime events (step completion) |

---

## 14. Telemetry Hooks

| Property | Value |
|---|---|
| trace_id propagation | Yes — carried through all model calls, skill calls, and delegation |
| Event logging | Plan, step, skill, subagent, recommendation, governance_wait, termination |

---

## 15. Local / Air-Gapped Support

| Property | Value |
|---|---|
| Local NIM support | Yes — via ModelGateway (which supports local NIM endpoints) |
| Air-gapped deployment | Supported (no external API dependencies in the adapter layer) |

---

## Conclusion

The `deep-agents` package was not found on PyPI as of the audit date. The POC adapter
simulates Deep Agents framework behavior to evaluate architectural compatibility with
the MAIW AgentRuntime Protocol. The simulation demonstrates integration pattern only —
no real framework behavior, dependencies, performance, or operational characteristics
can be confirmed.

**Adoption Decision:** INSUFFICIENT EVIDENCE (package not available)
