# MAIW Connectors

Connectors implement the **Provider interface** for vendor-specific backend systems.

## Distinction: Provider vs Connector

```
MCP server (warehouse.equipment.get_status)
   ↓
Provider interface (EquipmentProvider Protocol)
   ↓
Connector implementation (e.g., SAPEWMEquipmentConnector)
```

- **Provider**: Vendor-neutral interface that MCP servers depend on. Lives in `mcp_servers/<domain>/provider.py`.
- **Connector**: Vendor-specific implementation that satisfies the Provider protocol. Lives here.

## Current Connectors

| Connector | Domain | Status |
|-----------|--------|--------|
| `generic/` | All | Template / reference implementation |
| `sap-ewm/` | Equipment, Inventory | FUTURE — not implemented |
| `manhattan/` | Inventory, Wave | FUTURE — not implemented |
| `blue-yonder/` | Wave, Labor | FUTURE — not implemented |

The **default provider** for all domains is `MAIWBackendAdapter` which calls
the MAIW PostgreSQL database directly. This is suitable for single-instance deployments.

## Interface Contract

Every connector must implement the Provider protocol for its domain:

```python
class EquipmentProvider(Protocol):
    async def get_status(self, request: EquipmentStatusRequest) -> EquipmentStatusResult: ...
    async def assign(self, request: EquipmentAssignRequest) -> EquipmentAssignResult: ...
    async def release(self, request: EquipmentReleaseRequest) -> EquipmentReleaseResult: ...
    async def schedule_maintenance(self, request: ...) -> ...: ...
```

See `packages/maiw-mcp/maiw_mcp/contracts/` for request/result types.
See `mcp_servers/<domain>/provider.py` for the Protocol definition.
