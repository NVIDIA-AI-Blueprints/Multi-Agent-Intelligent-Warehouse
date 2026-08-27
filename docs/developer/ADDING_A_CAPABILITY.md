# Adding a Domain Capability (MCP Tool + Skill)

A "capability" in MAIW is an operation exposed by an MCP server and wrapped
in a typed skill in `packages/maiw-skills`. This guide adds a new capability
to an existing domain (e.g., `labor`, `equipment`, `wave`, `inventory`).

If you need a new domain entirely, add an MCP server under `mcp_servers/` first,
then follow these same steps.

---

## Anatomy of a Capability

```
MCP server tool (mcp_servers/<domain>/server.py)    ← capability entry point
     ↓
MCP contracts (packages/maiw-mcp/maiw_mcp/contracts/<domain>.py)
     ↓
Skill (packages/maiw-skills/maiw_skills/<domain>/skills.py)
     ↓
Agent or ActionExecutor calls the skill
```

---

## Step 1 — Define the contract

Add request/result Pydantic models and a `CapabilityMetadata` entry to:

```
packages/maiw-mcp/maiw_mcp/contracts/<domain>.py
```

**Example — adding `warehouse.labor.get_shift_schedule`:**

```python
# In maiw_mcp/contracts/labor.py

class LaborShiftScheduleRequest(BaseModel):
    warehouse_id: str
    shift_date: str  # ISO 8601

class LaborShiftScheduleResult(BaseModel):
    shifts: list[dict]  # structure to match your MCP server response

LABOR_GET_SHIFT_SCHEDULE_METADATA = CapabilityMetadata(
    name="warehouse.labor.get_shift_schedule",
    domain="labor",
    capability_type=CapabilityType.READ,
    description="Returns the shift schedule for a given date.",
    risk_level=RiskLevel.low,
)
```

Export the new symbols from `maiw_mcp/contracts/__init__.py` (or from
the domain module's `__all__`).

---

## Step 2 — Implement the MCP tool

Register the tool in the FastMCP app in:

```
mcp_servers/<domain>/server.py
```

```python
@mcp.tool(name="warehouse.labor.get_shift_schedule")
async def get_shift_schedule(warehouse_id: str, shift_date: str) -> dict:
    provider = get_labor_provider()
    return await provider.get_shift_schedule(warehouse_id, shift_date)
```

Implement the backing method in `mcp_servers/<domain>/provider.py`.

---

## Step 3 — Write the skill

Add a skill class in:

```
packages/maiw-skills/maiw_skills/<domain>/skills.py
```

```python
class LaborShiftScheduleSkill:
    """Shift schedule lookup via warehouse.labor.get_shift_schedule."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: LaborShiftScheduleRequest,
        *,
        trace_id: str | None = None,
    ) -> LaborShiftScheduleResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            LABOR_GET_SHIFT_SCHEDULE_METADATA.name, payload
        )
        try:
            return LaborShiftScheduleResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                "warehouse.labor.get_shift_schedule result failed validation"
            ) from exc
```

Export it from `packages/maiw-skills/maiw_skills/<domain>/__init__.py`.

---

## Step 4 — Wire into the agent (if it's a read skill)

Read skills are injected into agents at construction. Add the skill as a
constructor parameter in the relevant agent
(`packages/maiw-agents/maiw_agents/<domain>/agent.py`) and call it from
`analyze_disruption()`.

---

## Step 5 — Write an executor (if it's a write skill)

Write skills must only be called from a `BaseActionExecutor` subclass after
the 4-guard check passes. Add the new action name to the executor's
`_ALLOWED_ACTIONS` frozenset and implement `_do_execute`.

See `packages/maiw-execution/` for existing executor examples.

---

## Step 6 — Add tests

- Unit test the skill in isolation (mock the `MAIWMCPClient`).
- Add a contract test in `tests/contract/` that validates request/response
  shapes against the MCP server (in-memory transport).
- If the capability can fail (network timeout, malformed response), add a
  fault profile in `tests/unit/reliability/`.

---

## Architecture invariants to preserve

- **Read skills never mutate.** `CapabilityType.READ` tools must not have
  side effects.
- **Write skills never bypass the executor.** Agents call proposal skills
  (which build `ActionProposal` locally, zero MCP calls). Only executors call
  write skills, and only after `DecisionEngine` returns `APPROVED`.
- **No fault injection in production packages.** Any fault simulation
  belongs in `tests/` or `apps/api/maiw_api/demo/`.
