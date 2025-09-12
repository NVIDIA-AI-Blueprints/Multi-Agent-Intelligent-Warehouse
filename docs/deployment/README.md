# Deployment Guide

## Overview

This guide covers deploying the Warehouse Operational Assistant in various environments, from local development to production Kubernetes clusters.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Kubernetes 1.24+ (for K8s deployment)
- Helm 3.0+ (for Helm charts)
- kubectl configured for your cluster

## Quick Start

### Local Development

1. **Clone the repository:**
```bash
git clone https://github.com/T-DevH/warehouse-operational-assistant.git
cd warehouse-operational-assistant
```

2. **Set up environment variables:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Start with Docker Compose:**
```bash
docker-compose up -d
```

4. **Access the application:**
- Web UI: http://localhost:3001
- API: http://localhost:8001
- API Docs: http://localhost:8001/docs

## Environment Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# Application Configuration
APP_NAME=Warehouse Operational Assistant
APP_VERSION=0.1.0
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# Database Configuration
DB_HOST=localhost
DB_PORT=5435
DB_NAME=warehouse_assistant
DB_USER=warehouse_user
DB_PASSWORD=warehouse_pass
DB_SSL_MODE=prefer

# Vector Database Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_PASSWORD=Milvus

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=redis_pass
REDIS_DB=0

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# NVIDIA NIMs Configuration
NIM_LLM_BASE_URL=http://localhost:8000/v1
NIM_LLM_API_KEY=your-nim-llm-api-key
NIM_EMBEDDINGS_BASE_URL=http://localhost:8001/v1
NIM_EMBEDDINGS_API_KEY=your-nim-embeddings-api-key

# External Integrations
WMS_BASE_URL=http://wms.example.com/api
WMS_API_KEY=your-wms-api-key
ERP_BASE_URL=http://erp.example.com/api
ERP_API_KEY=your-erp-api-key

# Monitoring Configuration
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
ENABLE_METRICS=true

# Security Configuration
CORS_ORIGINS=["http://localhost:3001", "http://localhost:3000"]
ALLOWED_HOSTS=["localhost", "127.0.0.1"]
```

### Environment-Specific Configurations

#### Development
```bash
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
DB_SSL_MODE=disable
CORS_ORIGINS=["http://localhost:3001", "http://localhost:3000"]
```

#### Staging
```bash
ENVIRONMENT=staging
DEBUG=false
LOG_LEVEL=INFO
DB_SSL_MODE=prefer
CORS_ORIGINS=["https://staging.warehouse-assistant.com"]
```

#### Production
```bash
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARN
DB_SSL_MODE=require
CORS_ORIGINS=["https://warehouse-assistant.com"]
```

## Docker Deployment

### Single Container Deployment

1. **Build the Docker image:**
```bash
docker build -t warehouse-assistant:latest .
```

2. **Run the container:**
```bash
docker run -d \
  --name warehouse-assistant \
  -p 8001:8001 \
  -p 3001:3001 \
  --env-file .env \
  warehouse-assistant:latest
```

### Multi-Container Deployment

Use the provided `docker-compose.yml`:

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

### Docker Compose Services

The `docker-compose.yml` includes:

- **warehouse-assistant**: Main application
- **postgres**: PostgreSQL database
- **timescaledb**: TimescaleDB extension
- **milvus**: Vector database
- **redis**: Caching layer
- **prometheus**: Metrics collection
- **grafana**: Monitoring dashboards
- **nginx**: Reverse proxy (optional)

## Kubernetes Deployment

### Prerequisites

1. **Create namespace:**
```bash
kubectl create namespace warehouse-assistant
```

2. **Create secrets:**
```bash
kubectl create secret generic warehouse-secrets \
  --from-literal=db-password=your-db-password \
  --from-literal=jwt-secret=your-jwt-secret \
  --from-literal=nim-llm-api-key=your-nim-key \
  --from-literal=nim-embeddings-api-key=your-embeddings-key \
  --namespace=warehouse-assistant
```

3. **Create config map:**
```bash
kubectl create configmap warehouse-config \
  --from-literal=environment=production \
  --from-literal=log-level=INFO \
  --from-literal=db-host=postgres-service \
  --from-literal=milvus-host=milvus-service \
  --namespace=warehouse-assistant
```

### Deploy with Helm

1. **Add the Helm repository:**
```bash
helm repo add warehouse-assistant https://charts.warehouse-assistant.com
helm repo update
```

2. **Install the chart:**
```bash
helm install warehouse-assistant warehouse-assistant/warehouse-assistant \
  --namespace warehouse-assistant \
  --set image.tag=0.1.0 \
  --set environment=production \
  --set replicas=3
```

3. **Upgrade the deployment:**
```bash
helm upgrade warehouse-assistant warehouse-assistant/warehouse-assistant \
  --namespace warehouse-assistant \
  --set image.tag=0.1.1
```

### Manual Kubernetes Deployment

1. **Deploy PostgreSQL:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: warehouse-assistant
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_DB
          value: warehouse_assistant
        - name: POSTGRES_USER
          value: warehouse_user
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: warehouse-secrets
              key: db-password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: warehouse-assistant
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

2. **Deploy the main application:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: warehouse-assistant
  namespace: warehouse-assistant
spec:
  replicas: 3
  selector:
    matchLabels:
      app: warehouse-assistant
  template:
    metadata:
      labels:
        app: warehouse-assistant
    spec:
      containers:
      - name: warehouse-assistant
        image: warehouse-assistant:0.1.0
        ports:
        - containerPort: 8001
        env:
        - name: DB_HOST
          value: postgres-service
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: warehouse-secrets
              key: db-password
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: warehouse-secrets
              key: jwt-secret
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/ready
            port: 8001
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: warehouse-assistant-service
  namespace: warehouse-assistant
spec:
  selector:
    app: warehouse-assistant
  ports:
  - port: 80
    targetPort: 8001
  type: LoadBalancer
```

## Database Setup

### PostgreSQL Setup

1. **Create database:**
```sql
CREATE DATABASE warehouse_assistant;
CREATE USER warehouse_user WITH PASSWORD 'warehouse_pass';
GRANT ALL PRIVILEGES ON DATABASE warehouse_assistant TO warehouse_user;
```

2. **Run migrations:**
```bash
# Using the migration CLI
python chain_server/cli/migrate.py up

# Or using Docker
docker run --rm \
  --network warehouse-assistant_default \
  -e DB_HOST=postgres \
  -e DB_PASSWORD=warehouse_pass \
  warehouse-assistant:latest \
  python chain_server/cli/migrate.py up
```

### TimescaleDB Setup

1. **Enable TimescaleDB extension:**
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

2. **Create hypertables:**
```sql
-- This is handled by the migration system
SELECT create_hypertable('telemetry_data', 'timestamp');
SELECT create_hypertable('operation_metrics', 'timestamp');
```

### Milvus Setup

1. **Start Milvus:**
```bash
docker run -d \
  --name milvus \
  -p 19530:19530 \
  -p 9091:9091 \
  milvusdb/milvus:latest
```

2. **Create collections:**
```python
# This is handled by the application startup
from chain_server.services.vector import vector_service
await vector_service.initialize_collections()
```

## Monitoring Setup

### Prometheus Configuration

1. **Create prometheus.yml:**
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'warehouse-assistant'
    static_configs:
      - targets: ['warehouse-assistant:8001']
    metrics_path: '/api/v1/metrics'
    scrape_interval: 5s
```

2. **Deploy Prometheus:**
```bash
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:latest
```

### Grafana Setup

1. **Start Grafana:**
```bash
docker run -d \
  --name grafana \
  -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  grafana/grafana:latest
```

2. **Import dashboards:**
- Access Grafana at http://localhost:3000
- Login with admin/admin
- Import the provided dashboard JSON files

## Security Configuration

### SSL/TLS Setup

1. **Generate certificates:**
```bash
# Self-signed certificate for development
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Production certificates (use Let's Encrypt or your CA)
certbot certonly --standalone -d warehouse-assistant.com
```

2. **Configure Nginx:**
```nginx
server {
    listen 443 ssl;
    server_name warehouse-assistant.com;
    
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    
    location / {
        proxy_pass http://warehouse-assistant-service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Firewall Configuration

```bash
# Allow only necessary ports
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 8001/tcp  # API (if direct access needed)
ufw enable
```

## Backup and Recovery

### Database Backup

1. **Create backup script:**
```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
DB_NAME="warehouse_assistant"

# Create backup
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME > $BACKUP_DIR/backup_$DATE.sql

# Compress backup
gzip $BACKUP_DIR/backup_$DATE.sql

# Keep only last 30 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete
```

2. **Schedule backups:**
```bash
# Add to crontab
0 2 * * * /path/to/backup.sh
```

### Application Backup

1. **Backup configuration:**
```bash
# Backup environment files
cp .env .env.backup.$(date +%Y%m%d)

# Backup Docker volumes
docker run --rm -v warehouse-assistant_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz -C /data .
```

### Recovery Procedures

1. **Database recovery:**
```bash
# Stop application
docker-compose down

# Restore database
gunzip -c backup_20240101_020000.sql.gz | psql -h $DB_HOST -U $DB_USER -d $DB_NAME

# Start application
docker-compose up -d
```

2. **Application recovery:**
```bash
# Restore from backup
docker-compose down
docker volume rm warehouse-assistant_postgres_data
docker run --rm -v warehouse-assistant_postgres_data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres_data_20240101.tar.gz -C /data
docker-compose up -d
```

## Troubleshooting

### Common Issues

1. **Database connection errors:**
```bash
# Check database status
docker-compose logs postgres

# Test connection
docker-compose exec postgres psql -U warehouse_user -d warehouse_assistant -c "SELECT 1;"
```

2. **Application startup errors:**
```bash
# Check application logs
docker-compose logs warehouse-assistant

# Check environment variables
docker-compose exec warehouse-assistant env | grep DB_
```

3. **Memory issues:**
```bash
# Check memory usage
docker stats

# Increase memory limits in docker-compose.yml
```

### Performance Tuning

1. **Database optimization:**
```sql
-- Analyze tables
ANALYZE;

-- Check slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
```

2. **Application optimization:**
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Monitor resource usage
docker stats warehouse-assistant
```

## Scaling

### Horizontal Scaling

1. **Scale application replicas:**
```bash
# Docker Compose
docker-compose up -d --scale warehouse-assistant=3

# Kubernetes
kubectl scale deployment warehouse-assistant --replicas=5
```

2. **Load balancer configuration:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: warehouse-assistant-service
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 8001
  selector:
    app: warehouse-assistant
```

### Vertical Scaling

1. **Increase resource limits:**
```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

## Maintenance

### Regular Maintenance Tasks

1. **Database maintenance:**
```bash
# Weekly VACUUM
docker-compose exec postgres psql -U warehouse_user -d warehouse_assistant -c "VACUUM ANALYZE;"

# Monthly REINDEX
docker-compose exec postgres psql -U warehouse_user -d warehouse_assistant -c "REINDEX DATABASE warehouse_assistant;"
```

2. **Log rotation:**
```bash
# Configure logrotate
sudo nano /etc/logrotate.d/warehouse-assistant
```

3. **Security updates:**
```bash
# Update base images
docker-compose pull
docker-compose up -d --build
```

## Support

For deployment support:

- **Documentation**: [https://docs.warehouse-assistant.com/deployment](https://docs.warehouse-assistant.com/deployment)
- **Issues**: [https://github.com/T-DevH/warehouse-operational-assistant/issues](https://github.com/T-DevH/warehouse-operational-assistant/issues)
- **Email**: support@warehouse-assistant.com
