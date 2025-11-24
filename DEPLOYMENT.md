# Deployment Guide

Complete deployment guide for the Warehouse Operational Assistant with Docker and Kubernetes (Helm) options.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Deployment Options](#deployment-options)
  - [Option 1: Docker Deployment](#option-1-docker-deployment)
  - [Option 2: Kubernetes/Helm Deployment](#option-2-kuberneteshelm-deployment)
- [Post-Deployment Setup](#post-deployment-setup)
- [Access Points](#access-points)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Local Development (Fastest Setup)

```bash
# 1. Clone repository
git clone https://github.com/T-DevH/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# 2. Setup environment
./scripts/setup/setup_environment.sh

# 3. Start infrastructure services
./scripts/setup/dev_up.sh

# 4. Run database migrations
source env/bin/activate
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/001_equipment_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/002_document_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/004_inventory_movements_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f scripts/setup/create_model_tracking_tables.sql

# 5. Create default users
python scripts/setup/create_default_users.py

# 6. Start API server
./scripts/start_server.sh

# 7. Start frontend (in another terminal)
cd src/ui/web
npm install
npm start
```

**Access:**
- Frontend: http://localhost:3001 (login: `admin` / `changeme`)
- API: http://localhost:8001
- API Docs: http://localhost:8001/docs

## Prerequisites

### For Docker Deployment
- Docker 20.10+
- Docker Compose 2.0+
- 8GB+ RAM
- 20GB+ disk space

### For Kubernetes/Helm Deployment
- Kubernetes 1.24+
- Helm 3.0+
- kubectl configured for your cluster
- 16GB+ RAM (recommended)
- 50GB+ disk space

### Common Prerequisites
- Python 3.9+ (for local development)
- Node.js 18+ and npm (for frontend)
- Git

## Environment Configuration

### Required Environment Variables

Create a `.env` file in the project root:

```bash
# Copy example file
cp .env.example .env

# Edit with your values
nano .env  # or your preferred editor
```

**Critical Variables:**

```bash
# Database Configuration
POSTGRES_USER=warehouse
POSTGRES_PASSWORD=changeme  # Change in production!
POSTGRES_DB=warehouse
DB_HOST=localhost
DB_PORT=5435

# Security (REQUIRED for production)
JWT_SECRET_KEY=your-strong-random-secret-minimum-32-characters
ENVIRONMENT=production  # Set to 'production' for production deployments

# Admin User
DEFAULT_ADMIN_PASSWORD=changeme  # Change in production!

# Vector Database (Milvus)
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_PASSWORD=Milvus

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# NVIDIA NIMs (optional)
NIM_LLM_BASE_URL=http://localhost:8000/v1
NIM_LLM_API_KEY=your-nim-llm-api-key
NIM_EMBEDDINGS_BASE_URL=http://localhost:8001/v1
NIM_EMBEDDINGS_API_KEY=your-nim-embeddings-api-key

# CORS (for frontend access)
CORS_ORIGINS=http://localhost:3001,http://localhost:3000
```

**⚠️ Security Notes:**
- **Development**: `JWT_SECRET_KEY` is optional (uses default with warnings)
- **Production**: `JWT_SECRET_KEY` is **REQUIRED** - application will fail to start if not set
- Always use strong, unique passwords in production
- Never commit `.env` files to version control

See [docs/secrets.md](docs/secrets.md) for detailed security configuration.

## Deployment Options

### Option 1: Docker Deployment

#### Single Container Deployment

```bash
# 1. Build Docker image
docker build -t warehouse-assistant:latest .

# 2. Run container
docker run -d \
  --name warehouse-assistant \
  -p 8001:8001 \
  -p 3001:3001 \
  --env-file .env \
  warehouse-assistant:latest
```

#### Multi-Container Deployment (Recommended)

Use Docker Compose for full stack deployment:

```bash
# 1. Start all services
docker-compose -f deploy/compose/docker-compose.dev.yaml up -d

# 2. View logs
docker-compose -f deploy/compose/docker-compose.dev.yaml logs -f

# 3. Stop services
docker-compose -f deploy/compose/docker-compose.dev.yaml down

# 4. Rebuild and restart
docker-compose -f deploy/compose/docker-compose.dev.yaml up -d --build
```

**Docker Compose Services:**
- **timescaledb**: TimescaleDB database (port 5435)
- **redis**: Caching layer (port 6379)
- **kafka**: Message broker (port 9092)
- **milvus**: Vector database (port 19530)
- **prometheus**: Metrics collection (port 9090)
- **grafana**: Monitoring dashboards (port 3000)

**Production Docker Compose:**

```bash
# Use production compose file
docker-compose -f deploy/compose/docker-compose.yaml up -d
```

#### Docker Deployment Steps

1. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

2. **Start infrastructure:**
   ```bash
   docker-compose -f deploy/compose/docker-compose.yaml up -d postgres redis milvus
   ```

3. **Run database migrations:**
   ```bash
   # Wait for services to be ready
   sleep 10
   
   # Run migrations
   docker-compose -f deploy/compose/docker-compose.yaml exec postgres psql -U warehouse -d warehouse -f /docker-entrypoint-initdb.d/000_schema.sql
   # ... (run other migration files)
   ```

4. **Create users:**
   ```bash
   docker-compose -f deploy/compose/docker-compose.yaml exec api python scripts/setup/create_default_users.py
   ```

5. **Start application:**
   ```bash
   docker-compose -f deploy/compose/docker-compose.yaml up -d
   ```

### Option 2: Kubernetes/Helm Deployment

#### Prerequisites Setup

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
     --from-literal=admin-password=your-admin-password \
     --namespace=warehouse-assistant
   ```

3. **Create config map:**
   ```bash
   kubectl create configmap warehouse-config \
     --from-literal=environment=production \
     --from-literal=log-level=INFO \
     --from-literal=db-host=postgres-service \
     --from-literal=milvus-host=milvus-service \
     --from-literal=redis-host=redis-service \
     --namespace=warehouse-assistant
   ```

#### Deploy with Helm

1. **Navigate to Helm chart directory:**
   ```bash
   cd deploy/helm/warehouse-assistant
   ```

2. **Install the chart:**
   ```bash
   helm install warehouse-assistant . \
     --namespace warehouse-assistant \
     --create-namespace \
     --set image.tag=latest \
     --set environment=production \
     --set replicaCount=3 \
     --set postgres.enabled=true \
     --set redis.enabled=true \
     --set milvus.enabled=true
   ```

3. **Upgrade deployment:**
   ```bash
   helm upgrade warehouse-assistant . \
     --namespace warehouse-assistant \
     --set image.tag=latest \
     --set replicaCount=5
   ```

4. **View deployment status:**
   ```bash
   helm status warehouse-assistant --namespace warehouse-assistant
   kubectl get pods -n warehouse-assistant
   ```

5. **Access logs:**
   ```bash
   kubectl logs -f deployment/warehouse-assistant -n warehouse-assistant
   ```

#### Helm Configuration

Edit `deploy/helm/warehouse-assistant/values.yaml` to customize:

```yaml
replicaCount: 3
image:
  repository: warehouse-assistant
  tag: latest
  pullPolicy: IfNotPresent

environment: production
logLevel: INFO

resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "1Gi"
    cpu: "500m"

postgres:
  enabled: true
  storage: 20Gi

redis:
  enabled: true

milvus:
  enabled: true
  storage: 50Gi

service:
  type: LoadBalancer
  port: 80
  targetPort: 8001
```

## Post-Deployment Setup

### Database Migrations

After deployment, run database migrations:

```bash
# Docker
docker-compose exec postgres psql -U warehouse -d warehouse -f /path/to/migrations/000_schema.sql

# Kubernetes
kubectl exec -it deployment/postgres -n warehouse-assistant -- psql -U warehouse -d warehouse -f /migrations/000_schema.sql
```

**Required migration files:**
- `data/postgres/000_schema.sql`
- `data/postgres/001_equipment_schema.sql`
- `data/postgres/002_document_schema.sql`
- `data/postgres/004_inventory_movements_schema.sql`
- `scripts/setup/create_model_tracking_tables.sql`

### Create Default Users

```bash
# Docker
docker-compose exec api python scripts/setup/create_default_users.py

# Kubernetes
kubectl exec -it deployment/warehouse-assistant -n warehouse-assistant -- python scripts/setup/create_default_users.py
```

**⚠️ Security Note:** Users are created securely via the setup script using environment variables. The SQL schema does not contain hardcoded password hashes.

### Verify Deployment

```bash
# Health check
curl http://localhost:8001/health

# API version
curl http://localhost:8001/api/v1/version

# Service status (Kubernetes)
kubectl get pods -n warehouse-assistant
kubectl get services -n warehouse-assistant
```

## Access Points

Once deployed, access the application at:

- **Frontend UI**: http://localhost:3001 (or your LoadBalancer IP)
  - **Login**: `admin` / password from `DEFAULT_ADMIN_PASSWORD`
- **API Server**: http://localhost:8001 (or your service endpoint)
- **API Documentation**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/health
- **Metrics**: http://localhost:8001/api/v1/metrics (Prometheus format)

### Default Credentials

**⚠️ Change these in production!**

- **UI Login**: `admin` / `changeme` (or `DEFAULT_ADMIN_PASSWORD`)
- **Database**: `warehouse` / `changeme` (or `POSTGRES_PASSWORD`)
- **Grafana** (if enabled): `admin` / `changeme` (or `GRAFANA_ADMIN_PASSWORD`)

## Monitoring & Maintenance

### Health Checks

The application provides multiple health check endpoints:

- `/health` - Simple health check
- `/api/v1/health` - Comprehensive health with service status
- `/api/v1/health/simple` - Simple health for frontend

### Prometheus Metrics

Metrics are available at `/api/v1/metrics` in Prometheus format.

**Configure Prometheus scraping:**

```yaml
scrape_configs:
  - job_name: 'warehouse-assistant'
    static_configs:
      - targets: ['warehouse-assistant:8001']
    metrics_path: '/api/v1/metrics'
    scrape_interval: 5s
```

### Database Maintenance

**Regular maintenance tasks:**

```bash
# Weekly VACUUM
docker-compose exec postgres psql -U warehouse -d warehouse -c "VACUUM ANALYZE;"

# Monthly REINDEX
docker-compose exec postgres psql -U warehouse -d warehouse -c "REINDEX DATABASE warehouse;"
```

### Backup and Recovery

**Database backup:**

```bash
# Create backup
docker-compose exec postgres pg_dump -U warehouse warehouse > backup_$(date +%Y%m%d).sql

# Restore backup
docker-compose exec -T postgres psql -U warehouse warehouse < backup_20240101.sql
```

**Kubernetes backup:**

```bash
# Backup
kubectl exec -n warehouse-assistant deployment/postgres -- pg_dump -U warehouse warehouse > backup.sql

# Restore
kubectl exec -i -n warehouse-assistant deployment/postgres -- psql -U warehouse warehouse < backup.sql
```

## Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Docker
docker-compose down
# Or change ports in docker-compose.yaml

# Kubernetes
kubectl get services -n warehouse-assistant
# Check for port conflicts
```

#### Database Connection Errors

```bash
# Check database status
docker-compose ps postgres
# Or
kubectl get pods -n warehouse-assistant | grep postgres

# Test connection
docker-compose exec postgres psql -U warehouse -d warehouse -c "SELECT 1;"
```

#### Application Won't Start

```bash
# Check logs
docker-compose logs api
# Or
kubectl logs -f deployment/warehouse-assistant -n warehouse-assistant

# Verify environment variables
docker-compose exec api env | grep -E "DB_|JWT_|POSTGRES_"
```

#### Password Not Working

1. Check `DEFAULT_ADMIN_PASSWORD` in `.env` or Kubernetes secrets
2. Recreate users: `python scripts/setup/create_default_users.py`
3. Default password is `changeme` if not set

#### Module Not Found Errors

```bash
# Rebuild Docker image
docker-compose build --no-cache

# Or reinstall dependencies
docker-compose exec api pip install -r requirements.txt
```

### Performance Tuning

**Database optimization:**

```sql
-- Analyze tables
ANALYZE;

-- Check slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
```

**Scaling:**

```bash
# Docker Compose
docker-compose up -d --scale api=3

# Kubernetes
kubectl scale deployment warehouse-assistant --replicas=5 -n warehouse-assistant
```

## Additional Resources

- **Security Guide**: [docs/secrets.md](docs/secrets.md)
- **API Documentation**: http://localhost:8001/docs (when running)
- **Architecture**: [README.md](README.md)
- **RAPIDS Setup**: [docs/forecasting/RAPIDS_SETUP.md](docs/forecasting/RAPIDS_SETUP.md) (for GPU-accelerated forecasting)

## Support

- **Issues**: [GitHub Issues](https://github.com/T-DevH/Multi-Agent-Intelligent-Warehouse/issues)
- **Documentation**: [docs/](docs/)
- **Main README**: [README.md](README.md)
