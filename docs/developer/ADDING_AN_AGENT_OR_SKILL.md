# Adding an Agent or Skill

## Adding a New Agent

An agent in MAIW is a class that:
1. Receives a `WarehouseStateSnapshot` and a query
2. Calls `ModelGateway.generate()` to reason over the snapshot
3. Returns a structured `ActionProposal` (or a reasoning result, for
   read-only agents)

Agents live in `packages/maiw-agents/maiw_agents/<domain>/`.

### Step 1 — Create the agent class

```
packages/maiw-agents/maiw_agents/my_domain/agent.py
```

```python
from __future__ import annotations
from maiw_models.gateway import ModelGateway
from maiw_models.models import ModelRequest, ReasoningLevel, RiskLevel
from maiw_mcp.contracts.actions import ActionProposal
from maiw_state.snapshot import WarehouseStateSnapshot

class MyDomainAgent:
    """
    Analyzes [describe concern] and proposes corrective actions.
    """

    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

    async def analyze(
        self,
        query: str,
        snapshot: WarehouseStateSnapshot,
        *,
        trace_id: str | None = None,
    ) -> ActionProposal | None:
        # Build a prompt from the snapshot state
        prompt = self._build_prompt(query, snapshot)

        response = await self._gateway.generate(
            ModelRequest(
                prompt=prompt,
                system="You are a warehouse operations AI...",
                reasoning_level=ReasoningLevel.STANDARD,
                risk_level=RiskLevel.medium,
                max_tokens=1500,
            ),
            trace_id=trace_id,
        )

        return self._parse_proposal(response.content, snapshot)

    def _build_prompt(self, query: str, snapshot: WarehouseStateSnapshot) -> str:
        # Assemble relevant state into a structured prompt
        ...

    def _parse_proposal(
        self, content: str, snapshot: WarehouseStateSnapshot
    ) -> ActionProposal | None:
        # Parse model output → typed ActionProposal
        # Return None if no action is warranted
        ...
```

### Step 2 — Wire into bootstrap

Add the agent to `apps/api/maiw_api/bootstrap.py`:

```python
from maiw_agents.my_domain.agent import MyDomainAgent

my_agent = MyDomainAgent(gateway=model_gateway)
runtime.register_agent("my_domain", my_agent)
```

### Step 3 — Add a router endpoint (if needed)

Add a router in `apps/api/maiw_api/routers/my_domain.py` and register it in
`apps/api/maiw_api/app.py`.

---

## Adding a New Skill to an Existing Agent

Skills are lightweight wrappers around a single MCP capability. They live in
`packages/maiw-skills/maiw_skills/<domain>/skills.py`.

### When to add a skill vs. calling MCP directly

Always add a skill. Agents must never call `MAIWMCPClient.invoke()` directly.
Skills encapsulate the contract validation, error translation, and telemetry.

### Skill anatomy

```python
class MyReadSkill:
    """One-liner describing what MCP tool this wraps."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: MyRequest,
        *,
        trace_id: str | None = None,
    ) -> MyResult:
        raw = await self._client.invoke("warehouse.domain.tool_name", request.model_dump())
        try:
            return MyResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(f"tool_name result validation failed: {exc}") from exc
```

Inject the skill into the agent's constructor:

```python
class MyDomainAgent:
    def __init__(self, gateway: ModelGateway, my_skill: MyReadSkill) -> None:
        self._gateway = gateway
        self._my_skill = my_skill
```

---

## Architecture invariants

| Rule | Where it applies |
|------|-----------------|
| Agents call **read skills only** during `analyze()` | No write MCP calls in agents |
| Write capabilities go through **executor 4-guard check** | `BaseActionExecutor._check_guards()` |
| Agents **propose** — they do not execute | Only `ActionExecutor.execute()` calls write skills |
| No `fault_id` checks in agent code | Fault injection is test/demo infrastructure only |
| ModelGateway is the only path to NIM | Never call `NIMClient` directly from an agent |

---

## Testing

Write an async unit test for your agent using a mock `ModelGateway` and a
stub snapshot:

```python
from unittest.mock import AsyncMock
from tests.unit.reliability.fault_framework.fakes import make_test_snapshot

async def test_my_agent_proposes_when_disrupted():
    mock_gateway = AsyncMock()
    mock_gateway.generate.return_value = FakeLLMResponse(content="...")
    agent = MyDomainAgent(gateway=mock_gateway)
    proposal = await agent.analyze("fix zone A1", make_test_snapshot())
    assert proposal is not None
    assert proposal.domain == "my_domain"
```
