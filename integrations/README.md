# MAIW Integrations

This directory classifies non-core systems that have significant external dependencies
or are not part of the core transactional `STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND` pipeline.

## Architectural Status

| Integration | Current location | Classification | Notes |
|-------------|-----------------|----------------|-------|
| `forecasting/` | `src/api/agents/forecasting/` | EXTERNAL INTEGRATION | Uses ModelGateway; not MCP transactional |
| `document/` | `src/api/agents/document/` | EXTERNAL INTEGRATION | OCR, NeMo Parse, embeddings, multimodal judge |
| `simulation/` | *(not yet implemented)* | FUTURE | |
| `optimization/` | *(not yet implemented)* | FUTURE | |
| `training/` | *(not yet implemented)* | FUTURE — SFT, GRPO | Heavy GPU dependency |

## Integration Boundary Rule

The core packages (`maiw-mcp`, `maiw-state`, `maiw-decision`, `maiw-models`, `maiw-skills`)
**must not** import from integrations at module load time. Integrations may import from core.

Heavy optional dependencies (`asyncpg`, `pymilvus`, `redis`, GPU runtimes) belong in
integrations, not in core packages.

## Forecasting

`ForecastingAgent` uses `ModelGateway` for inference but does not write warehouse state
through the `PROPOSE → DECIDE → EXECUTE` pipeline. It is a read/inference-only agent.

Classification: **EXTERNAL INTEGRATION** — not a core operational domain.

Future: consider whether forecasting outputs should feed `WarehouseState` as a
derived field (e.g., `ForecastState`) rather than being a standalone agent.

## Document Pipeline

The document pipeline (`OCR → NeMo Parse → embeddings → judge`) has heavy dependencies
on GPU inference runtimes, vector stores (pymilvus), and async databases (asyncpg).

Classification: **EXTERNAL INTEGRATION** — isolated from core transactional agents.
