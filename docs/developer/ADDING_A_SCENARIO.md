# Adding a Demo Scenario

A scenario is a YAML file in `apps/api/maiw_api/demo/scenarios/`. The
`DemoScenarioController` auto-discovers all `.yaml` files in that directory —
no registration step required.

---

## Step 1 — Create the YAML file

```
apps/api/maiw_api/demo/scenarios/my_new_scenario.yaml
```

### Minimal template

```yaml
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
name: my_new_scenario             # must match filename stem (no spaces)
display_name: "My New Scenario"   # shown in the UI Demo Control Bar
description: >
  One paragraph describing the disruption and what the agent should do.
tags: [demo]
rng_seed: 42                      # fixed seed → deterministic simulation
clock_offset_seconds: 3600        # how far into a hypothetical shift (in seconds)

initial_state:
  inventory:
    - sku: "SKU-1001"
      name: "Example Item"
      zone: "A1"
      location_id: "A-01-01"
      quantity_available: 1000
      quantity_reserved: 100
      reorder_point: 200

  equipment:
    - asset_id: "AGV-01"
      equipment_type: "agv"
      model: "Locus Origin"
      zone: "A1"
      status: "available"
      battery_pct: 90.0

  workers:
    - worker_id: "w-001"
      username: "alice"
      full_name: "Alice Chen"
      role: "operator"
      status: "active"
      zone: "A1"
      current_task_id: null

  waves:
    - wave_id: "wave-001"
      priority: "high"
      status: "pending"
      carrier_cutoff_minutes: 60
      tasks_total: 10
      tasks_completed: 0
      assigned_workers: []
      assigned_equipment: []

timed_events: []   # optional: list of events that fire at simulation_time_seconds
```

### Adding timed events

Timed events mutate world state at a given simulation time. They are useful
for simulating progressive failures:

```yaml
timed_events:
  - simulation_time_seconds: 300   # 5 min in
    event_type: equipment_fault
    target_id: AGV-01
    payload:
      status: offline
      fault_code: E_MOTOR_OVERTEMP

  - simulation_time_seconds: 600   # 10 min in
    event_type: worker_absence
    target_id: w-001
    payload:
      status: on_leave
```

Supported `event_type` values: `equipment_fault`, `worker_absence`,
`wave_priority_change`, `inventory_adjustment`.

---

## Step 2 — Verify it loads

Start the demo API and check the scenarios list:

```bash
./scripts/start_demo_mode.sh &
curl http://localhost:8001/api/v1/demo/scenarios | python3 -m json.tool
```

Your new scenario should appear in the list with its `name` and `display_name`.

---

## Step 3 — Test it

Run `my_new_scenario` through the full pipeline manually:

```bash
curl -X POST http://localhost:8001/api/v1/demo/start \
     -H "Content-Type: application/json" \
     -d '{"scenario": "my_new_scenario"}'

curl -X POST http://localhost:8001/api/v1/demo/analyze
```

Or use the Command Center UI: select your scenario from the Demo Control Bar
and click START.

---

## Step 4 — Freeze the baseline (if it becomes a canonical scenario)

If this scenario is used for reliability or counterfactual evaluation, freeze
its baseline metrics in `tests/unit/reliability/test_scenario_001_baseline.py`
(by analogy). A frozen baseline catches accidental simulation drift.

---

## Design checklist

- [ ] `name` matches the filename stem (no spaces, lowercase, underscores)
- [ ] `rng_seed` is fixed (do not use `random`)
- [ ] Initial state creates a clear disruption that MAIW can address
- [ ] The disruption is resolvable by one of the three agents (Equipment, Operations, Safety)
- [ ] `description` explains what the operator should observe
- [ ] No real database or MCP connections are assumed (all via SimulationProviders)
