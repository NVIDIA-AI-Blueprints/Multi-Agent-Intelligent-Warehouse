# Adding a Model Provider

MAIW routes all inference through `ModelGateway` in `packages/maiw-models`.
The gateway accepts a provider that implements the `call()` interface. The
only built-in provider is `NIMProvider` (wraps `NIMClient` → NVIDIA API).

Use this guide to add a second provider — for example, a local Ollama
endpoint, a vLLM server, or a stub provider for testing.

---

## Provider interface

A provider is any object with this async method:

```python
async def call(
    self,
    *,
    model_id: str,
    request: ModelRequest,
    capability: ModelCapability,
) -> LLMResponse:
    ...
```

Where:
- `model_id` — the resolved model ID string (e.g. `"my-org/my-model-7b"`)
- `request` — `maiw_models.models.ModelRequest` (`messages`, `temperature`, `max_tokens`, …)
- `capability` — `maiw_models.models.ModelCapability` (role, reasoning level)
- return — `maiw_models.providers.nim_client.LLMResponse`
  (`.content: str`, `.usage: dict`, `.model: str`, `.finish_reason: str`,
  `.provider_model` — the model ID the endpoint reported; the gateway discards
  any response whose `provider_model` is missing or differs from `model_id`)

Raise `ModelTimeout` for deadline/timeout failures, `ModelUnavailable` for
service-down conditions, and `ModelResponseError` for malformed responses.
All three are in `maiw_models.errors`.

---

## Step 1 — Write the provider

```
packages/maiw-models/maiw_models/providers/my_provider.py
```

```python
from __future__ import annotations
import httpx
from ..errors import ModelResponseError, ModelTimeout, ModelUnavailable
from ..models import ModelCapability, ModelRequest
from .nim_client import LLMResponse

class MyProvider:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url
        self._api_key = api_key

    async def call(
        self,
        *,
        model_id: str,
        request: ModelRequest,
        capability: ModelCapability,
    ) -> LLMResponse:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": model_id,
                        "messages": request.messages,
                        "max_tokens": request.max_tokens or 2000,
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise ModelTimeout("MyProvider timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"MyProvider HTTP error: {exc}") from exc

        try:
            choice = data["choices"][0]
        except (KeyError, IndexError) as exc:
            raise ModelResponseError(f"Unexpected response shape: {data}") from exc

        return LLMResponse(
            content=choice["message"]["content"],
            usage=data.get("usage", {}),
            model=model_id,
            finish_reason=choice.get("finish_reason", "stop"),
            provider_model=data.get("model"),
        )
```

---

## Step 2 — Register a model role (optional)

The `ModelRouter` in `maiw_models.router` picks a role (`lightning`, `nano`,
`super`, `ultra`) and the gateway passes that role's resolved `model_id` to
your provider — you don't need to change the router. Enable the roles your
provider serves with `NEMOTRON_<ROLE>_ENABLED=true|false`.

`NEMOTRON_<ROLE>_MODEL` (e.g. `NEMOTRON_SUPER_MODEL`) can only select a model
ID listed for that role in `APPROVED_DEPLOYMENTS`
(`packages/maiw-models/maiw_models/deployment.py`); any other ID fails closed
with `ModelPolicyViolation` before the provider is called. Adding a new model
is a reviewed code change to that table, and only Nemotron 3 / 3.5
generations are accepted.

Role selection lives in `ModelRouter._select_role()` and `_FALLBACK_CHAIN`
(`maiw_models/router.py`); role capabilities live in
`maiw_models/registry.py`.

---

## Step 3 — Wire into bootstrap

`get_model_gateway()` always builds the NIM provider, so construct the gateway
directly with your provider in `apps/api/maiw_api/bootstrap.py`:

```python
from maiw_models.providers.my_provider import MyProvider

my_provider = MyProvider(
    base_url=os.getenv("MY_PROVIDER_URL", "http://localhost:11434"),
    api_key=os.getenv("MY_PROVIDER_API_KEY", ""),
)
from maiw_models import ModelGateway, ModelRegistry, ModelRouter

registry = ModelRegistry()
runtime.model_gateway = ModelGateway(
    provider=my_provider,
    registry=registry,
    router=ModelRouter(registry),
    nim_circuit=runtime.nim_circuit,
)
```

---

## Step 4 — Test

Write a unit test that constructs your provider with a mock `httpx` transport
and asserts:
- happy path returns `LLMResponse` with `.content`
- timeout raises `ModelTimeout`
- 503 response raises `ModelUnavailable`

Use `StubNIMProvider` in `tests/unit/reliability/fault_framework/fakes.py`
as a reference — it implements the same interface for test scenarios.

---

## What NOT to do

- Do not add retry logic inside the provider. `ModelGateway` owns retry
  policy (and currently defers retries to circuit breaker recovery, not
  explicit loops).
- Do not add fault-injection code in production providers. Use the
  `StubNIMProvider` pattern in test/demo infrastructure.
- Do not read `NVIDIA_API_KEY` directly from `os.environ` inside a provider.
  Accept credentials as constructor parameters so tests can pass stubs.
