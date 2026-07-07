#!/usr/bin/env bash
set -euo pipefail

repo_root="${MAIW_ROOT:-/maiw}"
brev_dir="${repo_root}/deploy/brev"
compose_file="${brev_dir}/docker-compose.maiw.yaml"
env_file="${brev_dir}/.env"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if [ ! -f "$env_file" ]; then
  echo "Missing deploy/brev/.env. Run Configure Blueprint first." >&2
  exit 1
fi

if [ ! -f "$compose_file" ]; then
  echo "Missing ${compose_file}." >&2
  exit 1
fi

cd "$brev_dir"

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

run_quiet() {
  local label="$1"
  local output_file
  local status

  shift
  output_file="$(mktemp)"
  if "$@" >"$output_file" 2>&1; then
    rm -f "$output_file"
    return 0
  fi

  status="$?"
  echo "" >&2
  echo "${label} failed. Captured output:" >&2
  cat "$output_file" >&2
  rm -f "$output_file"
  return "$status"
}

echo "Stopping blueprint containers..."
run_quiet "Stopping blueprint containers" compose stop

echo ""
echo "Blueprint containers stopped. They will stay stopped until deployed or restarted."

echo ""
echo "Refreshing container status..."
MAIW_ROOT="$repo_root" "$script_dir/container-status.sh" || true
