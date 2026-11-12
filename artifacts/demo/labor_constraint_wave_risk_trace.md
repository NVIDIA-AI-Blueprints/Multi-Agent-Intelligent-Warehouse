# MAIW Trace — labor_constraint_wave_risk

Captured: 2026-11-12T20:02:36.494928+00:00  
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
trace_id    : 911f381b-bfa3-47fb-aac8-0d9ebfadd575
snapshot_id : 5f942c80-8021-402f-9c88-6f1b7fb00bfa
```

### OBSERVE
```
domains_assembled : []
snapshot_id       : 5f942c80-8021-402f-9c88-6f1b7fb00bfa
freshness         : None
```

### REASON
```
model_id           : nvidia/nemotron-3-ultra-550b-a55b
routing_rule       : high_reasoning
routing_reason     : reasoning=HIGH requires Super
model_latency_ms   : 29142.784982919693
severity           : critical
domains_affected   : ['wave', 'labor']
recommendations    : 2
skills_consulted   : ['warehouse.labor.allocate', 'warehouse.wave.reprioritize']
```

### ASSESS
**Summary:** DC-47 has 40 idle workers while 4 pending wave tasks remain unassigned, creating a labor allocation failure. Additionally, 4 tasks are formally at-risk with a carrier cutoff approaching in under 24 hours.

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
- objective: Assign idle workers to the 4 pending tasks that currently have no worker allocated
- rationale: 40 workers are idle while 4 pending tasks have assigned_to=null; this allocation failure is the primary bottleneck preventing work from starting

**rec[1]** `warehouse.wave.reprioritize` → `current_wave`
- domain   : wave
- priority : high
- objective: Reprioritize wave tasks to ensure at-risk tasks and carrier-cutoff deadlines are met first
- rationale: 4 tasks are formally at-risk and the nearest carrier cutoff is 2026-08-23T10:00:00Z; once workers are allocated, sequencing must align with deadline pressure

### PROPOSE
```
index: 0
action: warehouse.labor.allocate
proposal_id: 83105201-7b92-43fa-988c-c39dbe568183
risk_level: medium
---
index: 1
action: warehouse.wave.reprioritize
proposal_id: 79e48cdf-7cb6-4a04-88c6-fb655ab6c9fb
risk_level: medium
---
```

### DECIDE
```
index: 0
outcome: requires_human_approval
proposal_id: 83105201-7b92-43fa-988c-c39dbe568183
decision_id: 5e3065be-728e-42d8-8f54-d7c054d4b289
violations: [{'rule': 'approval.required', 'message': 'risk_level=medium with requires_approval=True requires human approval', 'details': {'risk_level': 'medium', 'requires_approval': True}}]
---
index: 1
outcome: requires_human_approval
proposal_id: 79e48cdf-7cb6-4a04-88c6-fb655ab6c9fb
decision_id: ac9605d9-965c-4d02-9efb-8db5b21690f8
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
time_to_decision_ms : 30445.8
time_to_execution_ms: 31.2
```

### OPERATOR APPROVAL
```
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=ac975cef-0de9-4a77-a7f6-156c74a7b1f2
---
capability   : warehouse.wave.reprioritize
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=e8f09e43-0d4d-4ff4-9cfb-895e21aa287f
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=27d7bb07-38af-4d8a-81d3-c4c6909de5ba
---
capability   : warehouse.wave.reprioritize
outcome      : SUCCESS  status=no_op
exec_success : True  exec_id=ad723b34-18fe-4c92-8f98-a523e1c2f79e
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=16ef72a7-e893-4f21-9bc9-724e6a00ac48
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=47741be9-c2f7-42ed-b219-65f87cddf2fd
---
capability   : warehouse.wave.reprioritize
outcome      : SUCCESS  status=no_op
exec_success : True  exec_id=8943cb2f-e4a6-44e7-bc29-fd7405745657
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=3c3c3d49-1542-4371-a7b5-3443b6c94a47
---
capability   : warehouse.wave.reprioritize
outcome      : SUCCESS  status=no_op
exec_success : True  exec_id=942da5d1-f288-405f-8982-8b912f2155e2
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=8280477a-c287-4251-ac65-e4502c79fbd4
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=de520b9a-919d-4ea0-816b-48289fb90e9b
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
*Capture duration: 211.1s wall time*