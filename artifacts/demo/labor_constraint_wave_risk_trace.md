# MAIW Trace — labor_constraint_wave_risk

Captured: 2026-08-24T16:21:53.028065+00:00  
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
labor_availability  : 66.7%
labor_utilization   : 50.0%
pending_backlog     : 5
wave_risk           : CRITICAL / 95.0
wave_completion     : 0.0%
simulated_throughput: 0.0 units/hr
proj_service_level  : 0.0%
equipment_oper      : 100.0%
```

## RUN MAIW
```
trace_id    : 88c56aa3-4a67-450e-b857-6efac6087281
snapshot_id : b5807b22-1098-43bb-b287-a93adc99eec4
```

### OBSERVE
```
domains_assembled : []
snapshot_id       : b5807b22-1098-43bb-b287-a93adc99eec4
freshness         : None
```

### REASON
```
model_id           : nvidia/nemotron-3-super-120b-a12b
routing_rule       : high_reasoning
routing_reason     : reasoning=HIGH requires Super
model_latency_ms   : 3777.101332321763
severity           : high
domains_affected   : ['wave', 'labor']
recommendations    : 1
skills_consulted   : ['warehouse.labor.allocate']
```

### ASSESS
**Summary:** All 4 workers are idle while 5 pending wave tasks remain unassigned, creating a labor constraint that puts 5 tasks at risk.

**Facts observed:**
- Equipment: 4 total, 4 available
- Labor: 4 total, 4 available, 0% utilization
- Wave tasks: 7 total, 5 pending, 2 in_progress, 5 at-risk
- UNASSIGNED PENDING TASKS: 5 pending wave tasks have no worker allocated (assigned_to=null); 4 workers are idle. Use warehouse.labor.allocate to assign workers to these tasks.

### RECOMMENDATIONS

**rec[0]** `warehouse.labor.allocate` → `task_id`
- domain   : labor
- priority : high
- objective: Assign idle workers to pending wave tasks to prevent delays
- rationale: 5 pending wave tasks have no worker allocated (assigned_to=null) while 4 workers are idle; allocating labor will reduce at-risk tasks.

### PROPOSE
```
index: 0
action: warehouse.labor.allocate
proposal_id: c31a23d4-23b8-4aec-93c5-921815530ba0
risk_level: medium
---
```

### DECIDE
```
index: 0
outcome: requires_human_approval
proposal_id: c31a23d4-23b8-4aec-93c5-921815530ba0
decision_id: ee0b1349-9730-4b0a-883d-5c69cfc4b65b
violations: [{'rule': 'approval.required', 'message': 'risk_level=medium with requires_approval=True requires human approval', 'details': {'risk_level': 'medium', 'requires_approval': True}}]
---
```

### PRE → POST KPI (analysis snapshot)
```
                        PRE      POST     Δ
  labor_avail %       66.7     66.7      0.0
  labor_util  %       50.0     50.0      0.0
  backlog                5        5        0
  wave_risk score     95.0     95.0      0.0
  wave_compl  %        0.0      0.0      0.0
```

### TIMING
```
time_to_detect_ms   : None
time_to_decision_ms : 4969.4
time_to_execution_ms: 24.9
```

### OPERATOR APPROVAL
```
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=46fe5731-a689-4c14-b326-5baa22b17044
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=6eac29af-8f81-4e87-a946-71b4b09d80eb
---
capability   : warehouse.labor.allocate
outcome      : FAILED  status=CAPACITY_UNAVAILABLE
exec_success : None  exec_id=—
---
capability   : warehouse.labor.allocate
outcome      : FAILED  status=CAPACITY_UNAVAILABLE
exec_success : None  exec_id=—
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=8963ff1b-10a3-4a88-8d25-fd5f40f854f6
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=4e3f05ae-bb92-46d4-96e9-e8989e1d17ab
---
capability   : warehouse.labor.allocate
outcome      : FAILED  status=CAPACITY_UNAVAILABLE
exec_success : None  exec_id=—
---
capability   : warehouse.labor.allocate
outcome      : SUCCESS  status=executed
exec_success : True  exec_id=d16c2e6a-0fe6-4329-bb7f-03fb067b06f3
---
```

## KPI TRAJECTORY
```
tick   sim_t  risk_level  risk_sc  backlog  wave_%  throughput  proj_svc
───────────────────────────────────────────────────────────────────────────
   1    5460    CRITICAL     95.0        3     0.0         0.0       0.0
   2    5520    CRITICAL     95.0        3     0.0         0.0       0.0
   3    5580    CRITICAL     95.0        3     0.0         0.0       0.0
   4    5640    CRITICAL     95.0        3     0.0         0.0       0.0
   5    5700         LOW     20.0        1    42.9         3.0       0.0
   6    5760        NONE      0.0        0    57.1         4.0       0.0 ◀ RECOVERY
   7    5820        NONE      0.0        0    71.4         5.0       0.0
```

## RECOVERY
```
detected_at_tick    : 6
sim_time_seconds    : 5760
time_to_recovery    : 300.0s  (5.0 sim-min)
wave_risk_at_recov  : NONE / 0.0
backlog_at_recov    : 0
wave_compl_at_recov : 57.1%
```

## FINAL STATE
```
sim_time            : 5820s  clock=2026-08-23T09:37:00+00:00
labor_availability  : 50.0%
labor_utilization   : 66.7%
pending_backlog     : 0
wave_risk           : NONE / 0.0
wave_completion     : 71.4%
simulated_throughput: 5.0 units/hr
proj_service_level  : 0.0%
```

## DELTA FROM DISRUPTION (T=0 → FINAL)
```
  backlog             ↓ -5
  wave_risk_score     ↓ -95.0
  wave_completion %   ↑ 71.4
  throughput (u/hr)   ↑ 5.0
  proj_svc_level %      0.0
  labor_util %        ↑ 16.7
```

---
*Capture duration: 27.5s wall time*