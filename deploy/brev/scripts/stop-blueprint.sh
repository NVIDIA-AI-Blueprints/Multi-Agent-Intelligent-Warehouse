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

echo "Stopping blueprint containers..."
compose stop

echo ""
echo "Blueprint containers stopped. They will stay stopped until deployed or restarted."
compose ps -a

echo ""
echo "Refreshing container status..."
MAIW_ROOT="$repo_root" "$script_dir/container-status.sh" || true
