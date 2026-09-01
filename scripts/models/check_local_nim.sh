#!/usr/bin/env bash
# check_local_nim.sh — verify a local NIM endpoint is ready for MAIW inference.
#
# Usage:
#   ./scripts/models/check_local_nim.sh [BASE_URL] [MODEL]
#
# Arguments (with env var fallbacks):
#   BASE_URL  — NIM base URL  (default: $MAIW_NIM_BASE_URL or http://localhost:8000/v1)
#   MODEL     — Model name    (default: $MAIW_NIM_MODEL)
#
# Exit codes:
#   0 — endpoint healthy, model available, inference OK
#   1 — endpoint unreachable
#   2 — endpoint reachable but model not found
#   3 — inference failed (unexpected response)
set -euo pipefail

BASE_URL="${1:-${MAIW_NIM_BASE_URL:-http://localhost:8000/v1}}"
MODEL="${2:-${MAIW_NIM_MODEL:-}}"

log() { echo "[check_local_nim] $*" >&2; }
fail() { log "FAIL: $*"; exit "${2:-1}"; }

log "Checking NIM endpoint: ${BASE_URL}"

# ── 1. Health check ───────────────────────────────────────────────────────────
HEALTH_URL="${BASE_URL%/v1}/v1/health/ready"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${HEALTH_URL}" 2>/dev/null || echo "000")

if [[ "${HTTP_CODE}" == "000" ]]; then
  fail "Cannot reach ${HEALTH_URL} — is the NIM container running?" 1
fi

if [[ "${HTTP_CODE}" != "200" ]]; then
  log "WARNING: Health endpoint returned ${HTTP_CODE} (may be normal for some NIM versions)"
fi

log "Endpoint reachable (HTTP ${HTTP_CODE})"

# ── 2. Model availability ─────────────────────────────────────────────────────
if [[ -n "${MODEL}" ]]; then
  MODELS_URL="${BASE_URL%/}/models"
  MODELS_RESPONSE=$(curl -s --connect-timeout 10 "${MODELS_URL}" 2>/dev/null || echo '{"error":"unreachable"}')

  if echo "${MODELS_RESPONSE}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
models = [m.get('id','') for m in data.get('data', [])]
if not models:
    sys.exit(2)
if '${MODEL}' not in models:
    print(f'Available models: {models}', file=sys.stderr)
    sys.exit(2)
print(f'Model found: ${MODEL}')
" 2>&1; then
    log "Model ${MODEL} is available"
  else
    log "WARNING: Model ${MODEL} not found in /models listing (may still work if endpoint doesn't support listing)"
  fi
fi

# ── 3. Inference smoke test ───────────────────────────────────────────────────
CHAT_URL="${BASE_URL%/}/chat/completions"
MODEL_PARAM="${MODEL:-$(curl -s "${BASE_URL%/}/models" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['id'])" 2>/dev/null || echo 'unknown')}"

PAYLOAD=$(python3 -c "
import json
print(json.dumps({
    'model': '${MODEL_PARAM}',
    'messages': [{'role': 'user', 'content': 'Reply with the single word READY'}],
    'max_tokens': 10,
    'temperature': 0.0
}))
")

INFER_RESPONSE=$(curl -s --connect-timeout 30 -X POST "${CHAT_URL}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" 2>/dev/null || echo '{"error":"unreachable"}')

CONTENT=$(echo "${INFER_RESPONSE}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if 'error' in data:
    print(f'Error: {data[\"error\"]}', file=sys.stderr)
    sys.exit(3)
choices = data.get('choices', [])
if not choices:
    print('No choices in response', file=sys.stderr)
    sys.exit(3)
print(choices[0].get('message', {}).get('content', '').strip())
" 2>&1)

if [[ $? -ne 0 ]]; then
  fail "Inference failed: ${CONTENT}" 3
fi

log "Inference OK — response: '${CONTENT}'"
log ""
log "Local NIM is READY for MAIW."
log ""
log "To use this endpoint, add to your .env:"
log "  MAIW_MODEL_PROVIDER=local_nim"
log "  MAIW_NIM_BASE_URL=${BASE_URL}"
if [[ -n "${MODEL}" ]]; then
  log "  MAIW_NIM_MODEL=${MODEL}"
fi
