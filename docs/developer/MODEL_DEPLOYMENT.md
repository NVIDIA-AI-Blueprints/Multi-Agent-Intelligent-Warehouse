# Model Deployment Guide

All agent and Copilot inference goes through `ModelGateway`. It routes each request to a model **role** and dispatches that role's approved model ID to one OpenAI-compatible endpoint. Two groups of settings control deployment:

| Setting | What it controls |
|---------|------------------|
| `MAIW_NIM_BASE_URL` (+ `MAIW_NIM_API_KEY`) | The endpoint every request is sent to. Unset → NVIDIA hosted (`LLM_NIM_URL`, default `https://integrate.api.nvidia.com/v1`, key `NVIDIA_API_KEY`). |
| `NEMOTRON_<ROLE>_ENABLED` | Which roles (`LIGHTNING`, `NANO`, `SUPER`, `ULTRA`) the router may select. The endpoint must serve the exact model ID of every enabled role. |

`MAIW_MODEL_PROVIDER` (`nvidia_hosted`, `local_nim`, `openai_compatible`, `enterprise`) is written by `scripts/models/setup_local_nim.sh` for reference, but **it is not read by the runtime** — it is informational only. Likewise `MAIW_NIM_MODEL` only replaces `LLM_MODEL` for callers that bypass `ModelGateway`; the gateway always sends the routed role's approved model ID (`NEMOTRON_<ROLE>_MODEL` may only select an ID from `APPROVED_DEPLOYMENTS` in `packages/maiw-models/maiw_models/deployment.py`; any other ID fails closed).

## NVIDIA Hosted (Default)

No additional configuration needed beyond `NVIDIA_API_KEY`. With the defaults, Lightning serves LOW and MEDIUM reasoning and Ultra serves HIGH reasoning and CRITICAL risk.

```env
NVIDIA_API_KEY=nvapi-...
# LLM_NIM_URL=https://integrate.api.nvidia.com/v1   # default
```

Get an API key at [build.nvidia.com](https://build.nvidia.com/).

## Local NIM

Run a NIM container on your own hardware, then point MAIW at it.

### Quick setup

```bash
./scripts/models/setup_local_nim.sh \
  --url http://localhost:8000/v1 \
  --model nvidia/nemotron-3-super-120b-a12b \
  --check
```

This writes `MAIW_NIM_BASE_URL` (plus the informational `MAIW_MODEL_PROVIDER` and `MAIW_NIM_MODEL`) to your `.env` and verifies the endpoint. It does not change which roles are enabled. Every request goes to `MAIW_NIM_BASE_URL`, so enable only the roles that endpoint serves. For a single self-hosted Super NIM:

```env
MAIW_NIM_BASE_URL=http://localhost:8000/v1
# MAIW_NIM_API_KEY=   # leave empty for local NIM without auth
NEMOTRON_SUPER_ENABLED=true
NEMOTRON_LIGHTNING_ENABLED=false   # this endpoint does not serve Lightning
NEMOTRON_ULTRA_ENABLED=false       # this endpoint does not serve Ultra
```

With only Super enabled, LOW (Lightning → Nano → Super), MEDIUM (Nano → Super) and HIGH/CRITICAL requests are all served by Super.

### Starting a NIM container (example)

```bash
docker run --gpus all --rm \
  -p 8000:8000 \
  -e NGC_API_KEY="${NGC_API_KEY}" \
  nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:latest
```

### Verify connectivity

```bash
./scripts/models/check_local_nim.sh http://localhost:8000/v1 nvidia/nemotron-3-super-120b-a12b
```

Exit codes: 0 = OK, 1 = unreachable, 2 = model not found, 3 = inference failed.

## OpenAI-Compatible Endpoint (vLLM, Ollama, etc.)

Any OpenAI-compatible server works if it serves the **exact approved Nemotron model IDs** of the enabled roles and reports that ID in its responses (the gateway verifies response identity). Other model families (e.g. Llama) are not approved and fail closed.

```env
MAIW_NIM_BASE_URL=http://localhost:8080/v1
# MAIW_NIM_API_KEY=your-key-if-required
# Enable only the roles this server serves, e.g. a server hosting nvidia/nemotron-3.5-lightning-30b-a3b
# and nvidia/nemotron-3-ultra-550b-a55b needs no changes to the defaults.
```

## Enterprise NIM

```env
MAIW_NIM_BASE_URL=https://nim.your-company.com/v1
MAIW_NIM_API_KEY=nvapi-...
# Set NEMOTRON_<ROLE>_ENABLED to match the models this fleet serves (see Local NIM above).
```

## Model Availability and EOL

The model registry controls which roles are active. Current status (v2.1.0):

| Role | Model | Status |
|------|-------|--------|
| lightning | `nvidia/nemotron-3.5-lightning-30b-a3b` | Deployed |
| nano | `nvidia/nemotron-3-nano-30b-a3b` | **EOL 2026-09-01** — disabled by default |
| super | `nvidia/nemotron-3-super-120b-a12b` | **Hosted EOL 2026-10-19** — disabled by default; self-hosted NIM only |
| ultra | `nvidia/nemotron-3-ultra-550b-a55b` | Deployed (default for HIGH reasoning and CRITICAL risk) |

With the defaults, MEDIUM-reasoning requests fall through Nano and Super to Lightning, and HIGH-reasoning or CRITICAL-risk requests fall through Super to Ultra. They never fall below a Super/Ultra-class model; with both disabled they fail closed. With Super enabled (self-hosted), MEDIUM, HIGH and CRITICAL route to Super as before v2.1.0. The `CopilotTurnResponse` exposes `requested_role`, `selected_role`, and `fallback_from`/`fallback_reason` so operators can see exactly which model served each request.

### Forcing nano on (not recommended)

```env
NEMOTRON_NANO_ENABLED=true
MAIW_NIM_BASE_URL=http://localhost:8000/v1  # an endpoint that serves nvidia/nemotron-3-nano-30b-a3b
```

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MAIW_MODEL_PROVIDER` | _(none)_ | Informational only (written by `setup_local_nim.sh`); not read by the runtime |
| `MAIW_NIM_BASE_URL` | _(none)_ | Overrides `LLM_NIM_URL` when set |
| `MAIW_NIM_MODEL` | _(none)_ | Overrides `LLM_MODEL` when set (callers that bypass ModelGateway only) |
| `MAIW_NIM_API_KEY` | _(none)_ | Overrides `NVIDIA_API_KEY` for LLM endpoint |
| `NEMOTRON_NANO_ENABLED` | `false` | Enable nano role (EOL; opt-in only) |
| `NEMOTRON_LIGHTNING_ENABLED` | `true` | Enable lightning role |
| `NEMOTRON_SUPER_ENABLED` | `false` | Enable super role (hosted EOL; self-hosted NIM only) |
| `NEMOTRON_ULTRA_ENABLED` | `true` | Enable ultra role (default high-capability role) |
| `NEMOTRON_<ROLE>_MODEL` | approved ID per role | May only select an ID listed in `APPROVED_DEPLOYMENTS`; anything else fails closed |
| `LLM_NIM_URL` | `https://integrate.api.nvidia.com/v1` | Base URL when MAIW_NIM_BASE_URL not set |
| `LLM_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | Model when MAIW_NIM_MODEL not set (callers that bypass ModelGateway) |
| `LLM_CLIENT_TIMEOUT` | `240` | Per-request timeout in seconds |
| `LLM_CACHE_ENABLED` | `true` | Enable response caching |
| `LLM_CACHE_TTL_SECONDS` | `300` | Cache TTL in seconds |
