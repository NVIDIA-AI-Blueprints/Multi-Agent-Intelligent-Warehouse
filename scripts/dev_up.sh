#!/bin/bash
set -euo pipefail

# Warehouse Operational Assistant - Development Infrastructure Setup
# Brings up TimescaleDB, Redis, Kafka, Milvus, MinIO, etcd for local development

echo "Starting Warehouse Operational Assistant development infrastructure..."

# Choose compose flavor
if docker compose version >/dev/null 2>&1; then 
    COMPOSE=(docker compose)
    echo "Using docker compose (plugin)"
else 
    COMPOSE=(docker-compose)
    echo "Using docker-compose (standalone)"
fi

# 1) Change TimescaleDB host port 5432 -> 5435 (idempotent)
echo "Configuring TimescaleDB port 5435..."
grep -q "5435:5432" docker-compose.dev.yaml || sed -i.bak "s/5432:5432/5435:5432/" docker-compose.dev.yaml

# Update .env file
if grep -q "^PGPORT=" .env; then
    sed -i.bak "s/^PGPORT=.*/PGPORT=5435/" .env
else
    echo "PGPORT=5435" >> .env
fi

# 2) Fully stop and remove any old containers to avoid the recreate bug
echo "Cleaning up existing containers..."
"${COMPOSE[@]}" -f docker-compose.dev.yaml down --remove-orphans
docker rm -f wosa-timescaledb >/dev/null 2>&1 || true

# 3) Bring up all services
echo "Starting infrastructure services..."
"${COMPOSE[@]}" -f docker-compose.dev.yaml up -d

# 4) Wait for TimescaleDB to be ready
echo "Waiting for TimescaleDB on host port 5435..."
until docker exec wosa-timescaledb pg_isready -U "${POSTGRES_USER:-warehouse}" -d "${POSTGRES_DB:-warehouse}" >/dev/null 2>&1; do
    sleep 1
done

echo "Infrastructure is ready!"
echo ""
echo "Service Endpoints:"
echo "  • TimescaleDB: postgresql://warehouse:warehousepw@localhost:5435/warehouse"
echo "  • Redis: localhost:6379"
echo "  • Milvus gRPC: localhost:19530"
echo "  • Milvus HTTP: localhost:9091"
echo "  • Kafka: localhost:9092"
echo "  • MinIO: localhost:9000 (console: localhost:9001)"
echo "  • etcd: localhost:2379"
echo ""
echo "Next steps:"
echo "  1. Run database migrations: PGPASSWORD=warehousepw psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql"
echo "  2. Start the API: ./RUN_LOCAL.sh"
echo "  3. Test endpoints: curl http://localhost:<PORT>/api/v1/health"