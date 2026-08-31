# MAIW Developer Getting Started

This guide walks through the MAIW v2 developer setup path. No PostgreSQL, Redis, Milvus, or Kafka required for Demo Mode.

For architecture depth, see [WAREHOUSE_WORLD_MODEL.md](../WAREHOUSE_WORLD_MODEL.md).

---

## 1. Prerequisites

- Python 3.10+
- Node.js 20+ (for the UI)
- NVIDIA API key (`nvapi-...`)

---

## 2. Install

```bash
git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse
cd Multi-Agent-Intelligent-Warehouse

pip install -e packages/maiw-world packages/maiw-state packages/maiw-agents \
            packages/maiw-decision packages/maiw-execution packages/maiw-mcp
```

---

## 3. Configure your API key

```bash
export NVIDIA_API_KEY=nvapi-your-key-here
```

Or add it to `.env` in the repo root.

---

## 4. Configure your warehouse

Warehouse worlds are defined by a YAML config. Two canonical configs ship with the repo:

| Config | Path | Description |
|--------|------|-------------|
| DC-47 (canonical) | `data/world-configs/dc47-demo.yaml` | 25k SKUs, 120 workers, 24 equipment |
| Small (fast) | `data/world-configs/small.yaml` | 100 SKUs — < 1s generation |

You can also use Python presets directly:
```python
from maiw_world.config import WarehouseWorldConfig
cfg = WarehouseWorldConfig.dc47_demo()   # canonical demo
cfg = WarehouseWorldConfig.small()       # fast local iteration
cfg = WarehouseWorldConfig.from_yaml("data/world-configs/dc47-demo.yaml")
```

### Custom worlds

Copy `data/world-configs/dc47-demo.yaml` and edit the values. Change `warehouse_id`, `dataset_id`, and `seed`. Every config + seed combination produces a unique, deterministic world.

---

## 5. Generate the DataPack

```bash
# Quick setup (validates existing pack or generates new one)
./scripts/setup_demo_world.sh

# Or run directly
python -m maiw_world generate --config data/world-configs/dc47-demo.yaml \
                               --output data/worlds/dc47-demo-v1
```

The generator is deterministic: same config + same seed = same world every time.

Progress output:
```
Generating facility...        done   (6 zones, 240 locations)
Generating inventory...       done   (25000 SKUs)
Generating labor...           done   (120 workers)
Generating equipment...       done   (24 units)
Generating orders...          done   (850 orders)
Generating waves...           done   (3 waves, 120 tasks)
Building historical events... done   (172 events)

Validating...                 PASS

DataPack written: data/worlds/dc47-demo-v1
```

---

## 6. Inspect the graph

```bash
# Entity/edge summary
python -m maiw_world inspect data/worlds/dc47-demo-v1

# Inspect a specific entity
python -m maiw_world inspect data/worlds/dc47-demo-v1 --entity DC-47
python -m maiw_world inspect data/worlds/dc47-demo-v1 --entity wave-000
```

The inspect command shows all fields, outgoing edges, and incoming edges for any entity ID in the graph.

---

## 7. Validate the DataPack

```bash
python -m maiw_world validate data/worlds/dc47-demo-v1
```

Validation checks:
1. **Manifest** — required fields present
2. **File checksums** — content matches `checksums.json`
3. **Semantic checksum** — graph content matches `manifest.json`
4. **Graph validity** — structural rules (no orphan edges, required relationships present)

Exit code 0 = PASS, 1 = FAIL.

---

## 8. List available scenarios

```bash
python -m maiw_world scenarios data/worlds/dc47-demo-v1
```

| Scenario | Type | Description |
|----------|------|-------------|
| `labor_constraint_wave_risk` | DataPack-native | Understaffed shift, wave at risk |
| `equipment_failure` | DataPack-native | Forklift offline |
| `healthy_baseline` | DataPack-native | All systems nominal |
| `stale_state` | Compatibility | healthy_baseline adapter |
| `state_drift` | Compatibility | healthy_baseline adapter |

> **Note:** `stale_state` and `state_drift` currently use a healthy_baseline compatibility adapter.
> Full migration is planned for a future phase.

---

## 9. Launch Demo Mode

```bash
./scripts/start_demo_mode.sh
```

In a separate terminal:
```bash
cd src/ui/web && npm start
```

Open http://localhost:3001/demo

**Recommended scenario order:**
1. `healthy_baseline` — confirm world is coherent
2. `labor_constraint_wave_risk` — the primary demo scenario (Scenario 001)

**What you'll see:** OBSERVE → REASON → PROPOSE → DECIDE → APPROVE → EXECUTE → OUTCOME

---

## 10. Reset and reproduce

To reset to a known state:
```bash
python -m maiw_world generate \
  --config data/world-configs/dc47-demo.yaml \
  --output data/worlds/dc47-demo-v1 \
  --overwrite
```

The `--overwrite` flag atomically replaces the existing DataPack.

To verify the checksum matches across machines or developer environments:
```bash
python -m maiw_world checksum data/worlds/dc47-demo-v1
```

---

## 11. Custom worlds

Create your own config YAML:

```yaml
warehouse_id: MY-WH
dataset_id: my-warehouse-v1
seed: 7

facility:
  zone_count: 4
  location_count: 100
  dock_door_count: 4

inventory:
  sku_count: 5000
  low_stock_pct: 0.05

labor:
  workers_per_shift: 20
  shift_count: 2

equipment:
  agv_count: 4
  forklift_count: 6

orders:
  daily_order_count: 200
  lines_per_order_mean: 3.0

waves:
  active_wave_count: 2
  strategy: fifo
  task_count: 40

history:
  history_days: 14
```

Then generate:
```bash
python -m maiw_world generate --config my-warehouse.yaml --output data/worlds/my-warehouse-v1
```

---

## Notebook walkthrough

For an interactive walkthrough, open:
```
notebooks/setup/maiw_v2_setup.ipynb
```

This notebook covers environment check, configuration, generation, graph inspection, validation, reproducibility, and scenario preview — all without any external databases.

---

## Legacy path

The pre-Phase 14 setup path (PostgreSQL, Redis, Milvus, Kafka) is documented in:
```
notebooks/setup/complete_setup_guide.ipynb
```

That notebook is deprecated for Demo Mode. Use `maiw_v2_setup.ipynb` instead.
