#!/usr/bin/env bash
set -euo pipefail

repo_root="${MAIW_ROOT:-/maiw}"
brev_dir="${repo_root}/deploy/brev"
compose_file="${brev_dir}/docker-compose.maiw.yaml"
env_file="${brev_dir}/.env"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

admin_password="${ADMIN_PASSWORD:-}"
user_password="${USER_PASSWORD:-}"

if [ ! -f "$env_file" ]; then
  echo "Missing deploy/brev/.env. Run Configure Blueprint first." >&2
  exit 1
fi

if [ ! -f "$compose_file" ]; then
  echo "Missing ${compose_file}." >&2
  exit 1
fi

validate_password() {
  local label="$1"
  local value="$2"
  local byte_count

  if [ -z "$value" ]; then
    return 0
  fi

  if ! LC_ALL=C printf '%s' "$value" | grep -Eq '^[[:print:]]+$'; then
    echo "${label} must contain printable ASCII characters only." >&2
    exit 2
  fi

  byte_count="$(LC_ALL=C printf '%s' "$value" | wc -c | tr -d ' ')"
  if [ "$byte_count" -gt 72 ]; then
    echo "${label} must be 72 bytes or fewer." >&2
    exit 2
  fi
}

validate_password "Admin password" "$admin_password"
validate_password "User password" "$user_password"

if [ -z "$admin_password" ] && [ -z "$user_password" ]; then
  echo "No passwords provided. Nothing to update."
  exit 0
fi

cd "$brev_dir"

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

echo "Checking container status before setting account passwords..."
MAIW_ROOT="$repo_root" "$script_dir/container-status.sh"

timescaledb_container="$(compose ps -q timescaledb 2>/dev/null | head -n 1 || true)"
if [ -z "$timescaledb_container" ] || [ "$(docker inspect -f '{{.State.Status}}' "$timescaledb_container" 2>/dev/null || true)" != "running" ]; then
  echo "" >&2
  echo "Cannot set account passwords until TimescaleDB is running." >&2
  exit 1
fi

export ADMIN_PASSWORD="$admin_password"
export USER_PASSWORD="$user_password"

echo ""
echo "Updating account passwords..."
compose run --rm --no-deps \
  -e PGHOST=timescaledb \
  -e PGPORT=5432 \
  -e ADMIN_PASSWORD \
  -e USER_PASSWORD \
  backend python scripts/setup/set_default_passwords.py

unset ADMIN_PASSWORD USER_PASSWORD

echo ""
echo "Account passwords updated."
