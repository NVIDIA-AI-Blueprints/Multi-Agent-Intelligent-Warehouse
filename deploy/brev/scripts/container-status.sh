#!/usr/bin/env bash
set -euo pipefail

repo_root="${MAIW_ROOT:-/maiw}"
brev_dir="${repo_root}/deploy/brev"
compose_file="${brev_dir}/docker-compose.maiw.yaml"
env_file="${brev_dir}/.env"
require_healthy=false

if [ "${1:-}" = "--require-healthy" ]; then
  require_healthy=true
fi

finish() {
  if [ "$require_healthy" = true ] && [ "${all_healthy:-false}" != true ]; then
    echo ""
    echo "Container status is not healthy." >&2
    exit 1
  fi

  exit 0
}

if [ ! -f "$env_file" ]; then
  all_healthy=false
  echo "⚪ Blueprint containers not deployed"
  echo "Run Configure Blueprint first."
  finish
fi

if [ ! -f "$compose_file" ]; then
  all_healthy=false
  echo "🟡 Container status unavailable"
  echo "Missing ${compose_file}."
  finish
fi

cd "$brev_dir"

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

services="$(compose config --services 2>/dev/null || true)"

if [ -z "$services" ]; then
  all_healthy=false
  echo "🟡 Container status unavailable"
  echo "Could not read Compose services."
  finish
fi

services="$(printf '%s\n' "$services" | LC_ALL=C sort)"
compose_config_json="$(compose config --format json 2>/dev/null || true)"

service_image() {
  local service="$1"

  if [ -z "$compose_config_json" ] || ! command -v jq >/dev/null 2>&1; then
    return 0
  fi

  printf '%s' "$compose_config_json" | jq -r --arg service "$service" '.services[$service].image // empty' 2>/dev/null
}

image_exists() {
  local image="$1"

  [ -n "$image" ] || return 1
  docker image inspect "$image" >/dev/null 2>&1
}

all_healthy=true

while IFS= read -r service; do
  [ -n "$service" ] || continue

  container_id="$(compose ps -a -q "$service" 2>/dev/null | head -n 1 || true)"

  if [ -z "$container_id" ]; then
    image="$(service_image "$service")"

    if image_exists "$image"; then
      echo "⚪ ${service}: image pulled, container not created"
    else
      echo "🔘 ${service}: container not created, image not pulled"
    fi

    all_healthy=false
    continue
  fi

  state="$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null || echo unknown)"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null || echo none)"

  case "${state}:${health}" in
    running:healthy|running:none)
      icon="🟢"
      detail="running"
      ;;
    running:starting|restarting:*)
      icon="🟡"
      detail="running / starting"
      all_healthy=false
      ;;
    running:unhealthy|dead:*)
      icon="🚨"
      detail="unhealthy/dead"
      all_healthy=false
      ;;
    running:*)
      icon="🟢"
      detail="running"
      ;;
    *)
      icon="⛔️"
      detail="stopped"
      all_healthy=false
      ;;
  esac

  echo "${icon} ${service}: ${detail}"
done <<EOF
$services
EOF

finish
