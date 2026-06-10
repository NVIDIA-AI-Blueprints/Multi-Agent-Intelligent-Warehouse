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

read_env() {
  key="$1"
  grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true
}

postgres_user="$(read_env POSTGRES_USER)"
postgres_db="$(read_env POSTGRES_DB)"
postgres_user="${postgres_user:-warehouse}"
postgres_db="${postgres_db:-warehouse}"

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

run_backend() {
  compose run --rm --no-deps \
    -e PGHOST=timescaledb \
    -e PGPORT=5432 \
    backend "$@"
}

run_backend_with_default_passwords() {
  compose run --rm --no-deps \
    -e PGHOST=timescaledb \
    -e PGPORT=5432 \
    -e DEFAULT_ADMIN_PASSWORD \
    -e DEFAULT_USER_PASSWORD \
    backend "$@"
}

random_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    date +%s%N | sha256sum | awk '{print substr($1, 1, 48)}'
  fi
}

psql_exec() {
  docker exec -i wosa-timescaledb \
    psql -v ON_ERROR_STOP=1 \
      -U "$postgres_user" \
      -d "$postgres_db" "$@"
}

echo "Checking container status before installing demo data..."
MAIW_ROOT="$repo_root" "$script_dir/container-status.sh" --require-healthy

echo ""
echo "WARNING: Install Demo Data will destroy all existing application data."
echo "It removes persisted Postgres, Redis, Kafka, etcd, MinIO, and Milvus data before reinstalling demo data."
echo "NIM model/cache directories are preserved."
echo ""

echo "Stopping and removing blueprint containers..."
compose down --remove-orphans

echo ""
echo "Deleting persisted app data..."
for dir in postgres redis kafka etcd minio milvus; do
  rm -rf "/ephemeral/maiw/${dir}"
  mkdir -p "/ephemeral/maiw/${dir}"
done
chmod 777 /ephemeral/maiw/kafka || true

echo ""
echo "Starting infrastructure services..."
compose up -d --wait --wait-timeout "${STAGE_INFRA_WAIT_TIMEOUT_SECONDS:-900}" \
  timescaledb redis kafka etcd minio milvus

echo ""
echo "Applying database migrations..."
migrations=(
  "${repo_root}/data/postgres/000_schema.sql"
  "${repo_root}/data/postgres/001_equipment_schema.sql"
  "${repo_root}/data/postgres/002_document_schema.sql"
  "${repo_root}/data/postgres/004_inventory_movements_schema.sql"
  "${repo_root}/scripts/setup/create_model_tracking_tables.sql"
)

for migration in "${migrations[@]}"; do
  if [ ! -f "$migration" ]; then
    echo "Missing migration ${migration}." >&2
    exit 1
  fi

  echo "Applying $(basename "$migration")..."
  psql_exec < "$migration"
done

echo ""
echo "Building backend utility image..."
compose build backend

echo ""
echo "Loading quick demo data..."
export DEFAULT_ADMIN_PASSWORD
export DEFAULT_USER_PASSWORD
DEFAULT_ADMIN_PASSWORD="$(random_password)"
DEFAULT_USER_PASSWORD="$(random_password)"
run_backend_with_default_passwords python scripts/data/quick_demo_data.py

echo ""
echo "Loading historical demand data..."
run_backend python scripts/data/generate_historical_demand.py

echo ""
echo "Creating default accounts..."
DEFAULT_ADMIN_PASSWORD="$(random_password)"
DEFAULT_USER_PASSWORD="$(random_password)"
run_backend_with_default_passwords python scripts/setup/create_default_users.py
unset DEFAULT_ADMIN_PASSWORD DEFAULT_USER_PASSWORD

echo ""
echo "Starting full blueprint stack..."
compose up -d --remove-orphans --wait --wait-timeout "${DEPLOY_WAIT_TIMEOUT_SECONDS:-3600}"

echo ""
echo "Demo data staging complete."
psql_exec -tAc "
  SELECT 'users=' || count(*) FROM users
  UNION ALL SELECT 'inventory_items=' || count(*) FROM inventory_items
  UNION ALL SELECT 'tasks=' || count(*) FROM tasks
  UNION ALL SELECT 'safety_incidents=' || count(*) FROM safety_incidents
  UNION ALL SELECT 'equipment_telemetry=' || count(*) FROM equipment_telemetry
  UNION ALL SELECT 'inventory_movements=' || count(*) FROM inventory_movements
  ORDER BY 1;
"

echo ""
compose ps

MAIW_ROOT="$repo_root" "$script_dir/container-status.sh" >/dev/null || true
