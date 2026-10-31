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

  tasks:
    - task_id: "task-001"
      task_type: "PICK"
      zone: "A1"
      status: "pending"
      assigned_to: null
      priority: "high"
      deadline: "2026-08-23T09:30:00+00:00"

timed_events: []   # optional: list of events that fire at offset_seconds
```

### Adding timed events

Timed events mutate world state at a given simulation time. They are useful
for simulating progressive failures:

```yaml
timed_events:
  - offset_seconds: 300   # 5 min in
    type: equipment_fault
    payload:
      asset_id: AGV-01
      new_status: offline
      fault_code: E_MOTOR_OVERTEMP

  - offset_seconds: 600   # 10 min in
    type: worker_absence
    payload:
      worker_id: w-001
      new_status: on_leave
```

Supported `type` values (`DemoScenarioController.inject` in
`apps/api/maiw_api/demo/controller.py`): `equipment_fault`,
`equipment_restore`, `low_stock`, `worker_absence`, `worker_return`,
`task_deadline`, `wave_delay`.

Scenario names listed in `SCENARIO_OVERLAYS`
(`apps/api/maiw_api/demo/world_loader.py`) start from the DataPack world; any
other scenario is seeded from its YAML `initial_state`.

---

## Step 2 — Verify it loads

Start the demo API (see the README Quickstart) and check the scenarios list:

```bash
MAIW_DEMO_MODE=true MAIW_PERSISTENCE_MODE=memory uvicorn maiw_api.app:app --port 8001 &
curl http://localhost:8001/api/v1/demo/scenarios | python3 -m json.tool
```

Your new scenario should appear in the list with its `name` and `display_name`.

---

## Step 3 — Test it

Run `my_new_scenario` through the full pipeline manually:

```bash
curl -X POST http://localhost:8001/api/v1/demo/scenario/my_new_scenario/start

curl -X POST http://localhost:8001/api/v1/demo/analyze
```

Or use the UI at http://localhost:3001/demo (OPERATIONS): select your
scenario and click START.

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
