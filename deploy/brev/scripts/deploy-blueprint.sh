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

echo "Checking blueprint status..."
set +e
status_output="$(MAIW_ROOT="$repo_root" "$script_dir/status.sh")"
status_code="$?"
set -e
printf '%s\n' "$status_output"

if [ "$status_code" -ne 0 ]; then
  echo "Cannot deploy until blueprint status verifies the NVIDIA API key." >&2
  exit 1
fi

cd "$brev_dir"

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

echo ""
echo "Pulling container images..."
compose pull --quiet --ignore-buildable

echo ""
echo "Building application images..."
compose build --quiet

echo ""
echo "Starting containers..."
compose up -d --quiet-pull --quiet-build --remove-orphans

echo ""
echo "Deployment complete. Containers are configured with restart: unless-stopped."

echo ""
echo "Refreshing container status..."
MAIW_ROOT="$repo_root" "$script_dir/container-status.sh" || true
