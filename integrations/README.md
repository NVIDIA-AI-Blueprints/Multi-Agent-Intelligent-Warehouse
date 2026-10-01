# MAIW Integrations

This directory classifies non-core systems that have significant external dependencies
or are not part of the core transactional `STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND` pipeline.

## Architectural Status

| Integration | Current location | Classification | Notes |
|-------------|-----------------|----------------|-------|
| `nemoclaw/` | `integrations/nemoclaw/` | EXTERNAL INTEGRATION | Sandbox containment boundary. Imports `maiw-agents`; nothing in `packages/` imports it |
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

## NemoClaw / OpenShell Sandbox

> OpenShell enforces the security boundary; NemoClaw packages and operates it;
> MAIW continues to define what the agent is allowed to do and remains the sole
> authority over warehouse actions.

`integrations/nemoclaw` adds a sandbox boundary around an existing MAIW agent
runtime. It renders `RuntimeCapabilityPolicy` into an enforceable sandbox
policy, defines the two messages that cross the boundary, and provides a
fail-closed `SandboxedAgentRuntime` decorator.

This is **containment, not migration**. `SandboxedAgentRuntime` wraps an
unmodified `AgentRuntime` and reimplements none of its semantics — if this
directory were deleted, capability enforcement, governance and procedure
persistence would be unchanged.

Classification: **EXTERNAL INTEGRATION** — optional, additive, one-directional.

Status: architecture and contracts implemented; **no runtime qualification** —
NemoClaw and OpenShell are not installed on the development host, and the
provisioners fail closed rather than pretending otherwise.

See [docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md](../docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md).

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
