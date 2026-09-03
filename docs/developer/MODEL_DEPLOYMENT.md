# Model Deployment Guide

MAIW supports four model deployment modes controlled by `MAIW_MODEL_PROVIDER`:

| Mode | When to use | Required env vars |
|------|-------------|-------------------|
| `nvidia_hosted` (default) | NVIDIA public cloud via `integrate.api.nvidia.com` | `NVIDIA_API_KEY` |
| `local_nim` | Self-hosted NIM on-prem (H100, A100, or DGX fleet) | `MAIW_NIM_BASE_URL`, `MAIW_NIM_MODEL` |
| `openai_compatible` | vLLM, Ollama, or any OpenAI-compatible endpoint | `MAIW_NIM_BASE_URL`, `MAIW_NIM_MODEL` |
| `enterprise` | Enterprise NIM with NGC private registry auth | `MAIW_NIM_BASE_URL`, `MAIW_NIM_MODEL`, `MAIW_NIM_API_KEY` |

## NVIDIA Hosted (Default)

No additional configuration needed beyond `NVIDIA_API_KEY`.

```env
NVIDIA_API_KEY=nvapi-...
LLM_NIM_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=nvidia/nemotron-3-super-120b-a12b
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

This writes to your `.env` and verifies the endpoint. Manual equivalent:

```env
MAIW_MODEL_PROVIDER=local_nim
MAIW_NIM_BASE_URL=http://localhost:8000/v1
MAIW_NIM_MODEL=nvidia/nemotron-3-super-120b-a12b
# MAIW_NIM_API_KEY=   # leave empty for local NIM without auth
```

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

```env
MAIW_MODEL_PROVIDER=openai_compatible
MAIW_NIM_BASE_URL=http://localhost:8080/v1
MAIW_NIM_MODEL=meta/llama-3.1-8b-instruct
# MAIW_NIM_API_KEY=your-key-if-required
```

## Enterprise NIM

```env
MAIW_MODEL_PROVIDER=enterprise
MAIW_NIM_BASE_URL=https://nim.your-company.com/v1
MAIW_NIM_MODEL=nvidia/nemotron-3-super-120b-a12b
MAIW_NIM_API_KEY=nvapi-...
```

## Model Availability and EOL

The model registry controls which roles are active. Current status (as of 2026-09-01):

| Role | Model | Status |
|------|-------|--------|
| lightning | `nvidia/nemotron-3.5-lightning-30b-a3b` | Deployed |
| nano | `nvidia/nemotron-3-nano-30b-a3b` | **EOL 2026-09-01** — disabled by default |
| super | `nvidia/nemotron-3-super-120b-a12b` | Deployed (primary) |
| ultra | `nvidia/nemotron-3-ultra-550b-a55b` | Deployed, opt-in |

When nano is unavailable, MEDIUM-reasoning requests fall through to Super via the fallback chain. The `CopilotTurnResponse` exposes `requested_role`, `selected_role`, and `fallback_from`/`fallback_reason` so operators can see exactly which model served each request.

### Forcing nano on (not recommended)

```env
NEMOTRON_NANO_ENABLED=true
MAIW_NIM_MODEL=nvidia/nemotron-3-nano-30b-a3b  # or your local nano endpoint
```

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MAIW_MODEL_PROVIDER` | `nvidia_hosted` | Deployment mode |
| `MAIW_NIM_BASE_URL` | _(none)_ | Overrides `LLM_NIM_URL` when set |
| `MAIW_NIM_MODEL` | _(none)_ | Overrides `LLM_MODEL` when set |
| `MAIW_NIM_API_KEY` | _(none)_ | Overrides `NVIDIA_API_KEY` for LLM endpoint |
| `NEMOTRON_NANO_ENABLED` | `false` | Enable nano role (EOL; opt-in only) |
| `NEMOTRON_LIGHTNING_ENABLED` | `true` | Enable lightning role |
| `NEMOTRON_SUPER_ENABLED` | `true` | Enable super role |
| `NEMOTRON_ULTRA_ENABLED` | `false` | Enable ultra role (high cost; opt-in) |
| `LLM_NIM_URL` | `https://integrate.api.nvidia.com/v1` | Base URL when MAIW_NIM_BASE_URL not set |
| `LLM_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | Model when MAIW_NIM_MODEL not set |
| `LLM_CLIENT_TIMEOUT` | `120` | Per-request timeout in seconds |
| `LLM_CACHE_ENABLED` | `true` | Enable response caching |
| `LLM_CACHE_TTL_SECONDS` | `300` | Cache TTL in seconds |
