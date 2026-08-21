# MAIW Dependency Boundaries

## Summary

MAIW (Multi-Agent Intelligent Warehouse) and `data-designer-engine` have
**incompatible MCP SDK version requirements** (`mcp>=2.0.0,<3` vs `mcp<2`).
This is not a runtime conflict because they are designed to run in separate
environments. This document records the boundary, the rationale, and the
deployment implications.

---

## Dependency Map

| Layer | Package | MCP SDK | Purpose |
|-------|---------|---------|---------|
| MAIW API / agents | `maiw-mcp` | `>=2.0.0,<3` | Warehouse agent MCP infrastructure |
| MAIW MCP servers | `mcp_servers/inventory`, `mcp_servers/equipment` | `>=2.0.0,<3` | MCP tool servers |
| Data Designer Engine | `data-designer-engine 0.5.6` | `>=1.26.0,<2` | Synthetic training-data generation |

### MAIW Core (`pyproject.toml`)

MAIW's core `pyproject.toml` does not declare `mcp` directly — it is a
transitive dependency through `maiw-mcp`. The `maiw-mcp` package pins:

```toml
dependencies = [
    "mcp>=2.0.0,<3",
    "pydantic>=2.0.0",
    "anyio>=4.0.0",
]
```

### data-designer-engine (`data-designer-engine 0.5.6`)

```
Requires-Dist: mcp>=1.26.0,<2
```

This is the NVIDIA NeMo synthetic data generation engine.  It is a
**training-time** tool that powers the `nvidia-wms-workshop` notebooks;
it has nothing to do with MAIW's runtime API server.

---

## Why There Is No Runtime Conflict

`data-designer-engine` is **not imported anywhere in the MAIW project**:

- Not listed in `pyproject.toml`, `requirements.txt`, or any lock file.
- Zero Python source files in `src/` import from `data_designer` or
  `data_designer_engine`.
- The conflict only appears as a pip resolver **warning** when both
  packages happen to be installed in the same development venv (the shared
  `/home/nvidia/nvidia-wms-workshop/.venv`).

The separation is **architectural**, not just conventional:

```
nvidia-wms-workshop/     ← data generation environment
├── nb01_run.py           uses data-designer-engine (mcp<2)
├── notebooks/
│   └── 01_data_designer.ipynb
└── .venv/                shared dev venv (conflict warning here)
    ├── mcp==2.0.0
    ├── data-designer-engine==0.5.6
    └── maiw-mcp==0.1.0

Multi-Agent-Intelligent-Warehouse/   ← MAIW runtime environment
├── src/api/              NO data-designer imports
├── mcp_servers/          uses mcp 2.0.0
└── packages/maiw-mcp/    declares mcp>=2.0.0,<3
```

---

## Deployment

In all production and staging deployments, the two subsystems run in
**separate containers with separate Python environments**:

```
┌──────────────────────────────────────────────┐
│  MAIW API Container                           │
│  python:3.11 — mcp==2.x installed            │
│  data-designer-engine: NOT present            │
│                                               │
│  src/api/  mcp_servers/  packages/maiw-mcp/  │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  Data Designer Container (training time only) │
│  python:3.12 — mcp<2 installed               │
│  MAIW src/: NOT present                       │
│                                               │
│  nvidia-wms-workshop notebooks / scripts      │
└──────────────────────────────────────────────┘
```

The shared dev venv is a local convenience, not a production artefact.

---

## Development Workaround

If the shared venv pip resolver warning is disruptive, use a separate
virtual environment for MAIW development:

```bash
# MAIW dev environment
cd /home/nvidia/Multi-Agent-Intelligent-Warehouse
python -m venv .venv
source .venv/bin/activate
pip install -e packages/maiw-mcp/ -e .

# nvidia-wms-workshop (data generation — separate venv)
cd /home/nvidia/nvidia-wms-workshop
source .venv/bin/activate
```

---

## Optional Integrations

These packages are optional — MAIW starts without them; they enable
additional capabilities when available:

| Package | Environment Variable | Capability |
|---------|---------------------|------------|
| `maiw-mcp` | `MAIW_MCP_SERVER_INVENTORY_URL` | Inventory lookup via MCP |
| `maiw-mcp` | `MAIW_MCP_SERVER_EQUIPMENT_URL` | Equipment status via MCP |
| (future) `opentelemetry-sdk` | `MAIW_OTEL_ENDPOINT` | Distributed tracing |

---

## Out of Scope

The following integrations are explicitly **not implemented** in MAIW:

- **SAP EWM connector** — placeholder for future `SAPEWMAdapter`
- **Manhattan Associates WMS connector** — placeholder for future adapter
- **OAuth / OIDC** — auth is at the API gateway layer, not inside agents
- **data-designer-engine** — training-time tool, separate environment
