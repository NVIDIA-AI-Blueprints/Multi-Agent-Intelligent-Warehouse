#!/usr/bin/env bash
# setup_local_nim.sh — configure MAIW to use a local NIM endpoint.
#
# Usage:
#   ./scripts/models/setup_local_nim.sh --url <BASE_URL> --model <MODEL_ID> [--api-key <KEY>]
#
# Options:
#   --url     NIM base URL including /v1   (required, e.g. http://localhost:8000/v1)
#   --model   Model name to use            (required, e.g. nvidia/nemotron-3-super-120b-a12b)
#   --api-key NGC API key (optional for public local NIM without auth)
#   --env     Path to .env file to update  (default: .env in repo root)
#   --check   Run check_local_nim.sh after configuring
#
# What it does:
#   1. Validates the provided URL and model
#   2. Writes MAIW_MODEL_PROVIDER, MAIW_NIM_BASE_URL, MAIW_NIM_MODEL to .env
#   3. Optionally runs a connectivity check
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

BASE_URL=""
MODEL=""
API_KEY=""
ENV_FILE="${REPO_ROOT}/.env"
RUN_CHECK=false

log()  { echo "[setup_local_nim] $*" >&2; }
usage() {
  cat >&2 <<EOF
Usage: $0 --url <BASE_URL> --model <MODEL_ID> [--api-key <KEY>] [--env <PATH>] [--check]

Examples:
  $0 --url http://localhost:8000/v1 --model nvidia/nemotron-3-super-120b-a12b
  $0 --url http://nim.internal:8080/v1 --model meta/llama-3.1-8b-instruct --check
  $0 --url https://nim.company.com/v1 --model nvidia/nemotron-3-super-120b-a12b --api-key nvapi-xxx
EOF
  exit 1
}

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)      BASE_URL="$2"; shift 2 ;;
    --model)    MODEL="$2"; shift 2 ;;
    --api-key)  API_KEY="$2"; shift 2 ;;
    --env)      ENV_FILE="$2"; shift 2 ;;
    --check)    RUN_CHECK=true; shift ;;
    -h|--help)  usage ;;
    *)          log "Unknown argument: $1"; usage ;;
  esac
done

[[ -z "${BASE_URL}" ]] && { log "ERROR: --url is required"; usage; }
[[ -z "${MODEL}" ]]    && { log "ERROR: --model is required"; usage; }

# ── Validate URL format ───────────────────────────────────────────────────────
if ! python3 -c "
from urllib.parse import urlparse
u = urlparse('${BASE_URL}')
assert u.scheme in ('http','https'), f'scheme must be http or https, got: {u.scheme}'
assert u.netloc, 'host is missing'
" 2>&1; then
  log "ERROR: Invalid URL format: ${BASE_URL}"
  exit 1
fi

# ── Update .env ───────────────────────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
  log "ERROR: .env file not found at ${ENV_FILE}"
  log "Copy .env.example to .env first: cp .env.example .env"
  exit 1
fi

log "Updating ${ENV_FILE}..."

# Remove existing MAIW_MODEL_PROVIDER / MAIW_NIM_* lines
python3 -c "
import re, pathlib
env_file = pathlib.Path('${ENV_FILE}')
lines = env_file.read_text().splitlines()
keep = [l for l in lines if not re.match(r'^MAIW_(MODEL_PROVIDER|NIM_BASE_URL|NIM_MODEL|NIM_API_KEY)\s*=', l)]
env_file.write_text('\n'.join(keep) + '\n')
"

# Append new values
cat >> "${ENV_FILE}" <<EOF

# ── LOCAL NIM CONFIGURATION (written by setup_local_nim.sh) ─────────────────
MAIW_MODEL_PROVIDER=local_nim
MAIW_NIM_BASE_URL=${BASE_URL}
MAIW_NIM_MODEL=${MODEL}
EOF

if [[ -n "${API_KEY}" ]]; then
  echo "MAIW_NIM_API_KEY=${API_KEY}" >> "${ENV_FILE}"
fi

log "Written to ${ENV_FILE}:"
log "  MAIW_MODEL_PROVIDER=local_nim"
log "  MAIW_NIM_BASE_URL=${BASE_URL}"
log "  MAIW_NIM_MODEL=${MODEL}"
[[ -n "${API_KEY}" ]] && log "  MAIW_NIM_API_KEY=<set>"

# ── Optional connectivity check ───────────────────────────────────────────────
if [[ "${RUN_CHECK}" == "true" ]]; then
  log ""
  log "Running connectivity check..."
  "${SCRIPT_DIR}/check_local_nim.sh" "${BASE_URL}" "${MODEL}"
else
  log ""
  log "Setup complete. Run the following to verify connectivity:"
  log "  ./scripts/models/check_local_nim.sh ${BASE_URL} ${MODEL}"
  log ""
  log "Then restart the API to pick up the new configuration:"
  log "  MAIW_DEMO_MODE=true env/bin/python -m uvicorn maiw_api.app:app --port 8001"
fi
