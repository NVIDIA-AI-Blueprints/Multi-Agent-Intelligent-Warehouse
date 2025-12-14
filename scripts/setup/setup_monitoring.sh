#!/bin/bash

# Setup script for Warehouse Operational Assistant Monitoring Stack
set -e

echo " Setting up Warehouse Operational Assistant Monitoring Stack..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo " Docker is not running. Please start Docker and try again."
    exit 1
fi

# Create necessary directories
echo "📁 Creating monitoring directories..."
mkdir -p monitoring/prometheus/rules
mkdir -p monitoring/grafana/dashboards
mkdir -p monitoring/grafana/datasources
mkdir -p monitoring/alertmanager

# Set proper permissions
chmod 755 monitoring/prometheus/rules
chmod 755 monitoring/grafana/dashboards
chmod 755 monitoring/grafana/datasources
chmod 755 monitoring/alertmanager

echo "🐳 Starting monitoring stack with Docker Compose..."

# Start the monitoring stack
docker-compose -f deploy/compose/docker-compose.monitoring.yaml up -d

echo " Waiting for services to start..."
sleep 10

# Check if services are running
echo " Checking service status..."

services=("warehouse-prometheus" "warehouse-grafana" "warehouse-node-exporter" "warehouse-cadvisor" "warehouse-alertmanager")

for service in "${services[@]}"; do
    if docker ps --format "table {{.Names}}" | grep -q "$service"; then
        echo " $service is running"
    else
        echo " $service is not running"
    fi
done

echo ""
echo " Monitoring stack setup complete!"
echo ""
echo " Access URLs:"
echo "  • Grafana: http://localhost:3000 (admin/\${GRAFANA_ADMIN_PASSWORD:-changeme})"
echo "  • Prometheus: http://localhost:9090"
echo "  • Alertmanager: http://localhost:9093"
echo "  • Node Exporter: http://localhost:9100"
echo "  • cAdvisor: http://localhost:8080"
echo ""
echo " Next steps:"
echo "  1. Access Grafana at http://localhost:3000"
echo "  2. Login with admin/\${GRAFANA_ADMIN_PASSWORD:-changeme}"
echo "  3. Import the warehouse dashboards from the 'Warehouse Operations' folder"
echo "  4. Configure alerting rules in Prometheus"
echo "  5. Set up notification channels in Alertmanager"
echo ""
echo " To stop the monitoring stack:"
echo "  docker-compose -f deploy/compose/docker-compose.monitoring.yaml down"
echo ""
echo " To view logs:"
echo "  docker-compose -f deploy/compose/docker-compose.monitoring.yaml logs -f"
