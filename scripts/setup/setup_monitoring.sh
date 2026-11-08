#!/bin/bash

# Start the optional monitoring stack (Prometheus, Grafana, Alertmanager and
# exporters) next to the MAIW dev stack. Run from the repository root after
# scripts/setup/dev_up.sh. See deploy/compose/docker-compose.monitoring.yaml.
set -euo pipefail

COMPOSE_FILE=deploy/compose/docker-compose.monitoring.yaml
ENV_FILE=deploy/compose/.env
NETWORK="${MAIW_COMPOSE_NETWORK:-compose_default}"
GRAFANA_PORT="${MAIW_GRAFANA_PORT:-3030}"

echo "Setting up the MAIW monitoring stack..."

if ! docker info > /dev/null 2>&1; then
    echo "Docker is not running. Start Docker and try again."
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Run this script from the repository root ($COMPOSE_FILE not found)."
    exit 1
fi

# Prometheus scrapes the API and datastores over the dev stack's network.
if ! docker network inspect "$NETWORK" > /dev/null 2>&1; then
    echo "Docker network '$NETWORK' not found. Start the dev stack first"
    echo "(scripts/setup/dev_up.sh), or set MAIW_COMPOSE_NETWORK to its network name."
    exit 1
fi

# Compose reads deploy/compose/.env; Grafana has no default admin password.
if [ -z "${GRAFANA_ADMIN_PASSWORD:-}" ] && ! grep -qE '^GRAFANA_ADMIN_PASSWORD=.+' "$ENV_FILE" 2>/dev/null; then
    echo "GRAFANA_ADMIN_PASSWORD is not set. Add it to $ENV_FILE, for example:"
    echo "  echo \"GRAFANA_ADMIN_PASSWORD=\$(openssl rand -hex 16)\" >> $ENV_FILE"
    exit 1
fi

if docker compose version > /dev/null 2>&1; then
    COMPOSE=(docker compose)
else
    COMPOSE=(docker-compose)
fi

"${COMPOSE[@]}" -f "$COMPOSE_FILE" up -d

echo "Waiting for services to start..."
sleep 10

services=(warehouse-prometheus warehouse-grafana warehouse-alertmanager
          warehouse-node-exporter warehouse-cadvisor
          warehouse-redis-exporter warehouse-postgres-exporter)
for service in "${services[@]}"; do
    if docker ps --format '{{.Names}}' | grep -qx "$service"; then
        echo "  $service is running"
    else
        echo "  $service is NOT running (see: ${COMPOSE[*]} -f $COMPOSE_FILE logs $service)"
    fi
done

echo ""
echo "Monitoring stack started:"
echo "  Grafana:      http://localhost:${GRAFANA_PORT}  (user admin, password GRAFANA_ADMIN_PASSWORD)"
echo "                dashboard 'MAIW - Overview' in the 'Warehouse Operations' folder"
echo "  Prometheus:   http://localhost:9090  (Status > Targets shows what is scraped)"
echo "  Alertmanager: http://localhost:9093  (no notifications are sent by default)"
echo ""
echo "Stop:  ${COMPOSE[*]} -f $COMPOSE_FILE down"
echo "Logs:  ${COMPOSE[*]} -f $COMPOSE_FILE logs -f"
