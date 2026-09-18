# Phase 18H Agent Governance Baseline Audit

**Date:** 2026-09-18  
**Branch:** feat/phase-18h-agent-sop-foundation  
**Auditor:** Phase 18H implementation  
**Baseline HEAD:** f56056a (WS3 ModelGateway Evaluation Lab)

---

## 1. Executive Summary

MAIW is currently **governed LLM/tool orchestration, not yet an explicit SOP-driven agent system**.

The CopilotService → GovernedActionOrchestrator → DecisionEngine → ActionExecutor path is
well-governed. However, three agents contain legacy `process_query()` pathways with direct
write capabilities that bypass governance. In production, these bypasses are **currently
dormant** (action_tools is not injected at bootstrap time), but the code paths exist and
must be closed.

**Governance verdict before Phase 18H:** PARTIALLY GOVERNED — write paths exist but are
dormant; no agent contract; no SOP artifacts; no task state; no delegation contracts.

---

## 2. Write Path Audit

| Caller | Capability | Read/Write | Goes through DecisionEngine? | Goes through ActionExecutor? | Status |
|--------|------------|------------|------------------------------|------------------------------|--------|
| `OperationsCoordinationAgent.analyze_disruption()` | LLM reasoning, returns `RecommendedAction` | READ/ANALYTICAL | N/A (no write) | N/A | COMPLIANT |
| `OperationsCoordinationAgent.process_query()` | orchestrates action tools | — | NO | NO | LEGACY (write path dormant — action_tools=None in production) |
| `OperationsCoordinationAgent._execute_action_tools()` → `assign_tasks` | write: task assignment | WRITE | NO | NO | VIOLATION (dormant — action_tools=None) |
| `OperationsCoordinationAgent._execute_action_tools()` → `generate_pick_wave` | write: wave creation | WRITE | NO | NO | VIOLATION (dormant) |
| `OperationsCoordinationAgent._execute_action_tools()` → `dispatch_equipment` | write: equipment dispatch | WRITE | NO | NO | VIOLATION (dormant) |
| `OperationsCoordinationAgent._execute_action_tools()` → `rebalance_workload` | write: workload rebalance | WRITE | NO | NO | VIOLATION (dormant) |
| `OperationsCoordinationAgent._execute_action_tools()` → `manage_shift_schedule` | write: shift management | WRITE | NO | NO | VIOLATION (dormant) |
| `OperationsCoordinationAgent._execute_action_tools()` → `dock_scheduling` | write: dock scheduling | WRITE | NO | NO | VIOLATION (dormant) |
| `OperationsCoordinationAgent._execute_action_tools()` → `optimize_pick_paths` | write: path optimization | WRITE | NO | NO | VIOLATION (dormant) |
| `OperationsCoordinationAgent._execute_action_tools()` → `publish_kpis` | write: KPI publish | WRITE | NO | NO | VIOLATION (dormant) |
| `SafetyComplianceAgent.process_query()` | orchestrates safety tools | — | NO | NO | LEGACY (dormant) |
| `SafetyComplianceAgent._execute_action_tools()` → `log_incident` | write: incident log | NON_OPERATIONAL_WRITE | NO | NO | INTENTIONAL EXCEPTION (audit log, auto-authorized) |
| `SafetyComplianceAgent._execute_action_tools()` → `start_checklist` | write: checklist | NON_OPERATIONAL_WRITE | NO | NO | INTENTIONAL EXCEPTION (admin record) |
| `SafetyComplianceAgent._execute_action_tools()` → `broadcast_alert` | write: PA broadcast | OPERATIONAL_WRITE | NO | NO | UNRESOLVED (emergency candidate) → routed to governance by default |
| `SafetyComplianceAgent._execute_action_tools()` → `lockout_tagout_request` | write: asset lockout | OPERATIONAL_WRITE | NO | NO | UNRESOLVED (emergency candidate) → routed to governance by default |
| `SafetyComplianceAgent._execute_action_tools()` → `create_corrective_action` | write: corrective tracking | NON_OPERATIONAL_WRITE | NO | NO | INTENTIONAL EXCEPTION (admin record) |
| `SafetyComplianceAgent._execute_action_tools()` → `retrieve_sds` | read: safety data sheet | READ | N/A | N/A | COMPLIANT |
| `SafetyComplianceAgent._execute_action_tools()` → `near_miss_capture` | write: near miss log | NON_OPERATIONAL_WRITE | NO | NO | INTENTIONAL EXCEPTION (safety audit log) |
| `SafetyComplianceAgent._execute_action_tools()` → `get_safety_procedures` | read: procedures | READ | N/A | N/A | COMPLIANT |
| `EquipmentAssetOperationsAgent.propose_equipment_assignment()` (state-aware) | write: equipment assign | WRITE | YES (DecisionEngine) | YES (action_executor) | COMPLIANT |
| `EquipmentAssetOperationsAgent.propose_equipment_release()` (state-aware) | write: equipment release | WRITE | YES | YES | COMPLIANT |
| `EquipmentAssetOperationsAgent.propose_schedule_maintenance()` (state-aware) | write: maintenance schedule | WRITE | YES | YES | COMPLIANT |
| `EquipmentAssetOperationsAgent._legacy_assign()` | write: direct equipment assign | WRITE | NO | NO | LEGACY (labeled, warning logged, only activated when state_provider=None) |
| `EquipmentAssetOperationsAgent._execute_action_tools()` → `schedule_maintenance` | write: maintenance | WRITE | NO | NO | VIOLATION (bypasses state-aware path when intent=maintenance) |
| `EquipmentAssetOperationsAgent._execute_action_tools()` → `release_equipment` | write: release | WRITE | NO | NO | VIOLATION (bypasses state-aware path when intent=release) |
| `CopilotService.act()` | governance delegation | — | YES (via orchestrator) | YES (via orchestrator) | COMPLIANT |
| `GovernedActionOrchestrator.govern()` | full governance lifecycle | WRITE | YES | YES | COMPLIANT |
| `ActionExecutor.execute()` (domain executors) | MCP write | WRITE | YES (post-decision) | YES | COMPLIANT |
| `LaborActionExecutor.execute()` | MCP: labor.assign | WRITE | YES | YES | COMPLIANT |
| `WaveActionExecutor.execute()` | MCP: wave.reprioritize | WRITE | YES | YES | COMPLIANT |
| `EquipmentActionExecutor.execute()` | MCP: equipment.assign | WRITE | YES | YES | COMPLIANT |
| `state_aware_ops.propose_labor_allocation()` | write via governance | WRITE | YES | YES (if approved) | COMPLIANT |
| `state_aware_ops.propose_wave_reprioritization()` | write via governance | WRITE | YES | YES (if approved) | COMPLIANT |
| `equipment/state_aware_ops.propose_equipment_assignment()` | write via governance | WRITE | YES | YES (if approved) | COMPLIANT |
| Demo scenario mutation (`demo/providers/`) | world state mutation | WRITE | NO | NO | LEGACY (demo-only, intentional, not production agent path) |
| `safety.router` `POST /safety/incidents` | DB write: incident record | NON_OPERATIONAL_WRITE | NO | NO | INTENTIONAL EXCEPTION (direct CRUD API, not agent path) |
| `operations.router` `POST /operations/tasks` | DB write: task record | NON_OPERATIONAL_WRITE | NO | NO | INTENTIONAL EXCEPTION (direct CRUD API, not agent path) |

---

## 3. Agent Inventory (Pre-18H)

| Agent | Module | Status | Governed path | SOP | Task state | Delegation |
|-------|--------|--------|---------------|-----|------------|------------|
| `OperationsCoordinationAgent` | `maiw_agents.operations.agent` | Active | analyze_disruption() is compliant; process_query() is legacy | None | None | None |
| `SafetyComplianceAgent` | `maiw_agents.safety.agent` | Active (safety authority unclear) | process_query() is legacy | None | None | None |
| `EquipmentAssetOperationsAgent` | `maiw_agents.equipment.agent` | Active | state-aware path is compliant; legacy path present | None | None | None |
| `LaborAgent` | — | ABSENT | — | — | — | — |
| `WaveAgent` | — | ABSENT | — | — | — | — |
| `InventoryAgent` | — | ABSENT (skill only) | — | — | — | — |
| `ForecastingAgent` | — | Legacy/Partial | — | — | — | — |

---

## 4. Skill Inventory (Pre-18H)

| Skill | Module | Domain | Classification | Governance required |
|-------|--------|--------|----------------|---------------------|
| `InventoryLookupSkill` | `maiw_skills.inventory.lookup` | inventory | READ | No |
| `EquipmentStatusSkill` | `maiw_skills.equipment.skills` | equipment | READ | No |
| `EquipmentTelemetrySkill` | `maiw_skills.equipment.skills` | equipment | READ | No |
| `EquipmentAssignmentSkill` | `maiw_skills.equipment.skills` | equipment | PROPOSAL | Yes (builds ActionProposal) |
| `LaborCapacitySkill` | `maiw_skills.labor.skills` | labor | READ | No |
| `ProposeLaborAllocationSkill` | `maiw_skills.labor.skills` | labor | PROPOSAL | Yes (builds ActionProposal) |
| `WaveStatusSkill` | `maiw_skills.wave.skills` | wave | READ | No |
| `ProposeWaveReprioritizationSkill` | `maiw_skills.wave.skills` | wave | PROPOSAL | Yes (builds ActionProposal) |

---

## 5. Governance Architecture (Pre-18H)

**What works:**
- CopilotService is properly bounded (no ActionExecutor import)
- GovernedActionOrchestrator owns DecisionEngine + ActionExecutor
- EquipmentAssetOperationsAgent state-aware path is correct
- state_aware_ops (labor, wave, equipment) all go through DecisionEngine

**What is broken/missing:**
- OCA `process_query()` / `_execute_action_tools()` contain write bypasses (dormant but dangerous)
- EAO `_execute_action_tools()` maintenance and release intents bypass state-aware path
- No canonical AgentDefinition model
- No AgentTaskState
- No SOP artifacts (SOPs only exist as system prompts)
- No skill registry with read/write classification
- No delegation contracts
- No termination/escalation semantics
- No agent runtime protocol

---

## 6. Changes Required

### 18H.1 — Governance bypass closure
1. Deprecate `OperationsCoordinationAgent.process_query()` — add deprecation marker and
   make `_execute_action_tools()` a hard no-op that logs a warning and returns empty list.
   (The action_tools parameter is removed from the constructor or kept for compatibility
   but never used for writes.)
2. Fix `EquipmentAssetOperationsAgent._execute_action_tools()` — route maintenance and
   release intents through the state-aware `propose_*` methods.

### 18H.2 — AgentDefinition + AgentTaskState
Create `packages/maiw-agents/maiw_agents/contracts/` with canonical agent contract models.

### 18H.3 — SOPDefinition + loader + validator
Create typed SOP schema, YAML loader, and validation logic.

### 18H.4 — Skill registry
Create skill registry entries with read/write/proposal/emergency_write classifications.

### 18H.5–18H.9 — Agents, SOPs, delegation, runtime
Create LaborAgent, WaveAgent, delegation contracts, and minimal deterministic runtime.

### 18H.10 — Docs + release gate
Architecture docs, SOP docs, README update, test gate.

---

## 7. Safety Authority Model

The SafetyComplianceAgent's authority needs explicit classification:

| Capability | Classification | Authority |
|------------|---------------|-----------|
| `retrieve_sds` | OBSERVATIONAL | Auto-authorized |
| `get_safety_procedures` | OBSERVATIONAL | Auto-authorized |
| `log_incident` | NON_OPERATIONAL_WRITE | Policy-authorized (audit log) |
| `near_miss_capture` | NON_OPERATIONAL_WRITE | Policy-authorized (safety audit) |
| `create_corrective_action` | NON_OPERATIONAL_WRITE | Policy-authorized (admin record) |
| `start_checklist` | NON_OPERATIONAL_WRITE | Policy-authorized (admin record) |
| `broadcast_alert` | OPERATIONAL_WRITE | **UNRESOLVED** — may be emergency; route through governance by default until authority model established |
| `lockout_tagout_request` | OPERATIONAL_WRITE | **UNRESOLVED** — likely emergency authority; route through governance by default until explicit safety authority model defined |

Note: The SafetyComplianceAgent's `process_query()` write path is currently dormant
(action_tools=None in bootstrap). No immediate code change required for safety agent in
Phase 18H beyond classification documentation.

---

## 8. Provenance

- Audit performed on branch: `feat/phase-18h-agent-sop-foundation`
- nvidia/main HEAD at audit: `f56056a` (feat(models): ModelGateway Evaluation Lab — Workstream 3)
- PR #96 (World Explorer) present: YES
- PR #97 (ModelGateway Evaluation Lab) present: YES
