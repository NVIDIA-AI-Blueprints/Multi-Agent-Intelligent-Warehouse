# MAIW Trace — labor_constraint_wave_risk

Captured: 2026-11-12T22:33:28.719150+00:00  
Warehouse: `DC-47`  

## SCENARIO
```
name         : labor_constraint_wave_risk
display_name : Labor Constraint + Wave Risk
warehouse_id : DC-47
tags         : labor, wave, otif, risk, demo
```

## T=0 — DISRUPTED STATE
```
sim_time            : 5400s  clock=2026-08-23T09:30:00+00:00
labor_availability  : 98.3%
labor_utilization   : 66.1%
pending_backlog     : 119
wave_risk           : CRITICAL / 95.0
wave_completion     : 0.0%
simulated_throughput: 0.0 units/hr
proj_service_level  : 100.0%
equipment_oper      : 100.0%
```

## RUN MAIW
```
trace_id    : cce77793-0196-446f-8701-7449aa891fa2
snapshot_id : a4c12c69-02b8-4923-a509-3b54985b85b8
```

### OBSERVE
```
domains_assembled : []
snapshot_id       : a4c12c69-02b8-4923-a509-3b54985b85b8
freshness         : None
```

### REASON
```
model_id           : nvidia/nemotron-3-ultra-550b-a55b
routing_rule       : high_reasoning
routing_reason     : reasoning=HIGH requires Super
fallback_from      : super
fallback_reason    : role=super is disabled or policy-ineligible; escalated to ultra
model_latency_ms   : 20491.970974951982
severity           : critical
domains_affected   : ['wave', 'labor']
recommendations    : 2
skills_consulted   : ['warehouse.labor.allocate', 'warehouse.wave.reprioritize']
```

### ASSESS
**Summary:** DC-47 has a critical labor allocation failure: 40 workers are idle while 4 pending wave tasks remain unassigned, and 4 tasks are formally at-risk with a carrier cutoff at 2026-08-23T10:00:00Z. Equipment is fully available.

**Facts observed:**
- Equipment: 24 total, 24 available
- Labor: 118 total, 40 idle (active with no task), 66% utilization
- Wave tasks: 120 total, 119 pending, 1 in_progress, 4 at-risk
- Carrier cutoff (soonest deadline): 2026-08-23T10:00:00+00:00
- UNASSIGNED PENDING TASKS: 4 pending wave tasks have no worker allocated (assigned_to=null); 40 workers are idle. Use warehouse.labor.allocate to assign workers to these tasks.

### RECOMMENDATIONS

**rec[0]** `warehouse.labor.allocate` → `unassigned_pending_tasks`
- domain   : labor
- priority : critical
- objective: Assign idle workers to the 4 pending tasks that have no worker allocated so work can begin immediately
- rationale: 40 workers are idle while 4 pending tasks have assigned_to=null, creating an allocation failure that directly blocks wave progress despite ample labor capacity

**rec[1]** `warehouse.wave.reprioritize` → `at_risk_tasks`
- domain   : wave
- priority : high
- objective: Reprioritize the wave to ensure the 4 formally at-risk tasks are sequenced ahead of lower-priority work before carrier cutoff
- rationale: 4 tasks are flagged at-risk with a hard carrier deadline in ~2 hours; reprioritization ensures they are worked first once labor is allocated

### PROPOSE
```
index: 0
action: warehouse.labor.allocate
proposal_id: b9fc849a-4813-4596-9514-ee42ae3704b8
risk_level: medium
---
index: 1
action: warehouse.wave.reprioritize
proposal_id: e7fa245b-8688-47e5-9d46-7ae2ed317bd1
risk_level: medium
---
```

### DECIDE
```
index: 0
outcome: requires_human_approval
proposal_id: b9fc849a-4813-4596-9514-ee42ae3704b8
decision_id: e030347d-609f-49f5-a4c0-626319879de7
violations: [{'rule': 'approval.required', 'message': 'risk_level=medium with requires_approval=True requires human approval', 'details': {'risk_level': 'medium', 'requires_approval': True}}]
---
index: 1
outcome: requires_human_approval
proposal_id: e7fa245b-8688-47e5-9d46-7ae2ed317bd1
decision_id: 12a33d59-b5df-422a-a112-3a3d7bb823d2
violations: [{'rule': 'approval.required', 'message': 'risk_level=medium with requires_approval=True requires human approval', 'details': {'risk_level': 'medium', 'requires_approval': True}}]
---
```

### PRE → POST KPI (analysis snapshot)
```
                        PRE      POST     Δ
  labor_avail %       98.3     98.3      0.0
  labor_util  %       66.1     66.1      0.0
  backlog              119      119        0
  wave_risk score     95.0     95.0      0.0
  wave_compl  %        0.0      0.0      0.0
```

### TIMING
```
time_to_detect_ms   : None
time_to_decision_ms : 21729.2
time_to_execution_ms: 31.0
```

### OPERATOR APPROVAL
```
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=a657735f-eb8b-4e3a-a87e-85aa79745a32
---
capability   : warehouse.wave.reprioritize
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=4a659dcb-5444-4fc1-be27-4fb526e30a57
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=0b467f6b-ec17-4433-829a-4041b0e6d85b
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=546d3802-72d0-47c9-a6dd-f8dc39d2ea0f
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=c07a022b-39c1-4df4-8f15-21306942a168
---
capability   : warehouse.wave.reprioritize
outcome      : SUCCESS  status=no_op
exec_success : True  exec_id=1cdef854-a13d-49b0-976a-1516dae9c3e4
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=5e2c84b4-0c33-4b5a-83b5-8a33fb0b7c61
---
capability   : warehouse.wave.reprioritize
outcome      : SUCCESS  status=no_op
exec_success : True  exec_id=2938e05d-c4fd-4465-b9fe-65b66b0b06d7
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=b1210ee7-3d83-4861-8f43-33c94b1f5406
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=2ae2d603-047b-4499-960d-a976eaa35cef
---
```

## KPI TRAJECTORY
```
tick   sim_t  risk_level  risk_sc  backlog  wave_%  throughput  proj_svc
───────────────────────────────────────────────────────────────────────────
   1    5460    CRITICAL     95.0       40     0.0         0.0     100.0
   2    5520    CRITICAL     95.0       39     0.0         0.0     100.0
   3    5580    CRITICAL     95.0       38     0.0         0.0     100.0
   4    5640        NONE      0.0       23    24.2        29.0     100.0
   5    5700        NONE      0.0       22    25.8        31.0     100.0 ◀ RECOVERY
   6    5760        NONE      0.0       12    48.3        58.0     100.0
```

## RECOVERY
```
detected_at_tick    : 5
sim_time_seconds    : 5700
time_to_recovery    : 180.0s  (3.0 sim-min)
wave_risk_at_recov  : NONE / 0.0
backlog_at_recov    : 22
wave_compl_at_recov : 25.8%
```

## FINAL STATE
```
sim_time            : 5760s  clock=2026-08-23T09:36:00+00:00
labor_availability  : 97.5%
labor_utilization   : 42.7%
pending_backlog     : 12
wave_risk           : NONE / 0.0
wave_completion     : 48.3%
simulated_throughput: 58.0 units/hr
proj_service_level  : 100.0%
```

## DELTA FROM DISRUPTION (T=0 → FINAL)
```
  backlog             ↓ -107
  wave_risk_score     ↓ -95.0
  wave_completion %   ↑ 48.3
  throughput (u/hr)   ↑ 58.0
  proj_svc_level %      0.0
  labor_util %        ↓ -23.4
```

---
*Capture duration: 158.7s wall time*