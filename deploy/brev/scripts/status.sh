#!/usr/bin/env bash
set -euo pipefail

repo_root="${MAIW_ROOT:-/maiw}"
brev_dir="${repo_root}/deploy/brev"
env_file="${brev_dir}/.env"
always_zero=false

for arg in "$@"; do
  case "$arg" in
    --always-zero)
      always_zero=true
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 2
      ;;
  esac
done

finish() {
  local code="$1"

  if [ "$always_zero" = true ]; then
    exit 0
  fi

  exit "$code"
}

read_env() {
  key="$1"
  if [ -f "$env_file" ]; then
    grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true
  fi
}

if [ ! -f "$env_file" ]; then
  echo "🔴 NVIDIA API key not configured"
  finish 1
fi

api_key="${NVIDIA_API_KEY:-$(read_env NVIDIA_API_KEY)}"
api_base="${EMBEDDING_NIM_URL:-$(read_env EMBEDDING_NIM_URL)}"
api_base="${api_base:-https://integrate.api.nvidia.com/v1}"

if ! printf '%s' "$api_key" | grep -Eq '^nvapi-[A-Za-z0-9._-]+$'; then
  echo "🔴 NVIDIA API key not configured"
  finish 1
fi

http_code="$(
  curl -sS \
    -o /dev/null \
    -w '%{http_code}' \
    --connect-timeout 3 \
    --max-time 8 \
    -H "Authorization: Bearer ${api_key}" \
    -H "Accept: application/json" \
    "${api_base%/}/models" \
    2>/dev/null || true
)"

case "$http_code" in
  200)
    echo "🟢 NVIDIA API key verified"
    finish 0
    ;;
  401|403)
    echo "🔴 NVIDIA API key rejected"
    finish 1
    ;;
  000)
    echo "🟡 NVIDIA API key check unavailable - API timeout"
    finish 2
    ;;
  429)
    echo "🟡 NVIDIA API key check rate-limited"
    finish 2
    ;;
  *)
    echo "🟡 NVIDIA API key check inconclusive - HTTP ${http_code}"
    finish 2
    ;;
esac
