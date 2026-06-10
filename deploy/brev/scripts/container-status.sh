#!/usr/bin/env bash
set -euo pipefail

repo_root="${MAIW_ROOT:-/maiw}"
brev_dir="${repo_root}/deploy/brev"
compose_file="${brev_dir}/docker-compose.maiw.yaml"
env_file="${brev_dir}/.env"
require_healthy=false
allow_health_starting=false
status_code=0
always_zero=false

for arg in "$@"; do
  case "$arg" in
    --allow-health-starting)
      allow_health_starting=true
      ;;
    --require-healthy)
      require_healthy=true
      ;;
    --always-zero)
      always_zero=true
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 2
      ;;
  esac
done

mark_starting() {
  if [ "$status_code" -eq 0 ]; then
    status_code=2
  fi
}

mark_stopped() {
  status_code=1
}

finish() {
  if [ "$require_healthy" = true ] && [ "$status_code" -ne 0 ]; then
    echo ""
    echo "Container status is not healthy." >&2
  fi

  if [ "$always_zero" = true ]; then
    exit 0
  fi

  exit "$status_code"
}

if [ ! -f "$env_file" ]; then
  mark_stopped
  echo "⚪ Blueprint containers not deployed"
  echo "Run Configure Blueprint first."
  finish
fi

if [ ! -f "$compose_file" ]; then
  mark_starting
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
  mark_starting
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

    mark_stopped
    continue
  fi

  state="$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null || echo unknown)"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null || echo none)"

  case "${state}:${health}" in
    running:healthy|running:none)
      icon="🟢"
      detail="running"
      ;;
    running:starting)
      icon="🟡"
      detail="running / health starting"
      if [ "$allow_health_starting" != true ]; then
        mark_starting
      fi
      ;;
    restarting:*)
      icon="🟡"
      detail="restarting"
      mark_starting
      ;;
    running:unhealthy|dead:*)
      icon="🚨"
      detail="unhealthy/dead"
      mark_stopped
      ;;
    running:*)
      icon="🟢"
      detail="running"
      ;;
    *)
      icon="⛔️"
      detail="stopped"
      mark_stopped
      ;;
  esac

  echo "${icon} ${service}: ${detail}"
done <<EOF
$services
EOF

finish
