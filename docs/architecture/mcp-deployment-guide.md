# MCP Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying the Model Context Protocol (MCP) system in various environments. The MCP system is designed to be scalable, reliable, and easy to deploy across different infrastructure configurations.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Docker Deployment](#docker-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Production Deployment](#production-deployment)
6. [Monitoring and Logging](#monitoring-and-logging)
7. [Security Configuration](#security-configuration)
8. [Troubleshooting](#troubleshooting)
9. [Performance Optimization](#performance-optimization)

## Prerequisites

### System Requirements

#### Minimum Requirements
- **CPU**: 2 cores
- **RAM**: 4GB
- **Storage**: 20GB SSD
- **Network**: 100 Mbps

#### Recommended Requirements
- **CPU**: 4+ cores
- **RAM**: 8GB+
- **Storage**: 50GB+ SSD
- **Network**: 1 Gbps

### Software Dependencies

- **Python**: 3.11+
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **PostgreSQL**: 13+
- **Redis**: 6.0+
- **TimescaleDB**: 2.0+
- **Milvus**: 2.0+

### External Services

- **Message Queue**: Kafka or RabbitMQ
- **Monitoring**: Prometheus + Grafana
- **Logging**: ELK Stack or similar
- **Load Balancer**: Nginx or HAProxy

## Environment Setup

### 1. Clone Repository

```bash
git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse
```

### 2. Create Virtual Environment

```bash
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Create environment files for different deployment stages:

#### Development (.env.dev)
```bash
# Database Configuration
DATABASE_URL=postgresql://${POSTGRES_USER:-warehouse}:${POSTGRES_PASSWORD:-changeme}@localhost:5435/${POSTGRES_DB:-warehouse}
REDIS_URL=redis://localhost:6379/0

# MCP Configuration
MCP_SERVER_HOST=localhost
MCP_SERVER_PORT=8000
MCP_CLIENT_TIMEOUT=30
MCP_DISCOVERY_INTERVAL=30

# Service Discovery
SERVICE_DISCOVERY_ENABLED=true
SERVICE_REGISTRY_URL=http://localhost:8001

# Monitoring
MONITORING_ENABLED=true
PROMETHEUS_ENDPOINT=http://localhost:9090
GRAFANA_ENDPOINT=http://localhost:3000

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=json

# Security
JWT_SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here
```

#### Staging (.env.staging)
```bash
# Database Configuration
DATABASE_URL=postgresql://${POSTGRES_USER:-warehouse}:${POSTGRES_PASSWORD:-changeme}@staging-db:5432/warehouse
REDIS_URL=redis://staging-redis:6379/0

# MCP Configuration
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
MCP_CLIENT_TIMEOUT=60
MCP_DISCOVERY_INTERVAL=60

# Service Discovery
SERVICE_DISCOVERY_ENABLED=true
# Security: Use HTTPS for external-facing services in production
# HTTP is acceptable for internal Docker service URLs (same network)
SERVICE_REGISTRY_URL=http://staging-registry:8001

# Monitoring
MONITORING_ENABLED=true
# Security: Use HTTPS for external-facing services in production
# HTTP is acceptable for internal Docker service URLs (same network)
PROMETHEUS_ENDPOINT=http://staging-prometheus:9090
GRAFANA_ENDPOINT=http://staging-grafana:3000

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security
JWT_SECRET_KEY=your-staging-secret-key
ENCRYPTION_KEY=your-staging-encryption-key
```

#### Production (.env.prod)
```bash
# Database Configuration
DATABASE_URL=postgresql://warehouse:${DB_PASSWORD}@prod-db:5432/warehouse
REDIS_URL=redis://prod-redis:6379/0

# MCP Configuration
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
MCP_CLIENT_TIMEOUT=120
MCP_DISCOVERY_INTERVAL=120

# Service Discovery
SERVICE_DISCOVERY_ENABLED=true
# Security: Use HTTPS for external-facing services in production
# HTTP is acceptable for internal Docker service URLs (same network)
SERVICE_REGISTRY_URL=http://prod-registry:8001

# Monitoring
MONITORING_ENABLED=true
# Security: Use HTTPS for external-facing services in production
# HTTP is acceptable for internal Docker service URLs (same network)
PROMETHEUS_ENDPOINT=http://prod-prometheus:9090
GRAFANA_ENDPOINT=http://prod-grafana:3000

# Logging
LOG_LEVEL=WARNING
LOG_FORMAT=json

# Security
JWT_SECRET_KEY=${JWT_SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
```

## Docker Deployment

### 1. Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # Database Services
  postgres:
    image: timescale/timescaledb:latest-pg13
    environment:
      POSTGRES_DB: warehouse
      POSTGRES_USER: warehouse
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
    ports:
      - "5435:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./data/postgres/migrations:/docker-entrypoint-initdb.d
    networks:
      - warehouse_network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - warehouse_network

  milvus:
    image: milvusdb/milvus:latest
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
    volumes:
      - milvus_data:/var/lib/milvus
    depends_on:
      - etcd
      - minio
    networks:
      - warehouse_network

  etcd:
    image: quay.io/coreos/etcd:latest
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    volumes:
      - etcd_data:/etcd
    networks:
      - warehouse_network

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY:-minioadmin}
    command: minio server /minio_data
    volumes:
      - minio_data:/minio_data
    networks:
      - warehouse_network

  # MCP Services
  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-warehouse}:${POSTGRES_PASSWORD:-changeme}@postgres:5432/warehouse
      - REDIS_URL=redis://redis:6379/0
      - MCP_SERVER_HOST=0.0.0.0
      - MCP_SERVER_PORT=8000
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    networks:
      - warehouse_network
    restart: unless-stopped

  mcp-client:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-warehouse}:${POSTGRES_PASSWORD:-changeme}@postgres:5432/warehouse
      - REDIS_URL=redis://redis:6379/0
      - MCP_SERVER_URL=http://mcp-server:8000
    depends_on:
      - mcp-server
    networks:
      - warehouse_network
    restart: unless-stopped

  # Adapter Services
  erp-adapter:
    build:
      context: .
      dockerfile: Dockerfile.adapter
    environment:
      - ADAPTER_TYPE=erp
      - MCP_SERVER_URL=http://mcp-server:8000
      - ERP_CONNECTION_STRING=${ERP_CONNECTION_STRING}
    depends_on:
      - mcp-server
    networks:
      - warehouse_network
    restart: unless-stopped

  wms-adapter:
    build:
      context: .
      dockerfile: Dockerfile.adapter
    environment:
      - ADAPTER_TYPE=wms
      - MCP_SERVER_URL=http://mcp-server:8000
      - WMS_CONNECTION_STRING=${WMS_CONNECTION_STRING}
    depends_on:
      - mcp-server
    networks:
      - warehouse_network
    restart: unless-stopped

  iot-adapter:
    build:
      context: .
      dockerfile: Dockerfile.adapter
    environment:
      - ADAPTER_TYPE=iot
      - MCP_SERVER_URL=http://mcp-server:8000
      - IOT_CONNECTION_STRING=${IOT_CONNECTION_STRING}
    depends_on:
      - mcp-server
    networks:
      - warehouse_network
    restart: unless-stopped

  # Monitoring Services
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=200h'
      - '--web.enable-lifecycle'
    networks:
      - warehouse_network

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
    networks:
      - warehouse_network

  # Load Balancer
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - mcp-server
    networks:
      - warehouse_network

volumes:
  postgres_data:
  redis_data:
  milvus_data:
  etcd_data:
  minio_data:
  prometheus_data:
  grafana_data:

networks:
  warehouse_network:
    driver: bridge
```

### 2. Dockerfile Configuration

#### Dockerfile.mcp
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/simple || exit 1

# Start command
CMD ["python", "-m", "src.api.app"]
```

#### Dockerfile.adapter
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 adapteruser && chown -R adapteruser:adapteruser /app
USER adapteruser

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Start command
CMD ["python", "-m", "src.api.services.mcp.adapters.${ADAPTER_TYPE}_adapter"]
```

### 3. Deploy with Docker Compose

```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f mcp-server

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Kubernetes Deployment

### 1. Namespace Configuration

Create `k8s/namespace.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: warehouse-mcp
  labels:
    name: warehouse-mcp
```

### 2. ConfigMap Configuration

Create `k8s/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-config
  namespace: warehouse-mcp
data:
  DATABASE_URL: "postgresql://${POSTGRES_USER:-warehouse}:${POSTGRES_PASSWORD}@postgres-service:5432/${POSTGRES_DB:-warehouse}"
  REDIS_URL: "redis://redis-service:6379/0"
  MCP_SERVER_HOST: "0.0.0.0"
  MCP_SERVER_PORT: "8000"
  MCP_CLIENT_TIMEOUT: "30"
  MCP_DISCOVERY_INTERVAL: "30"
  SERVICE_DISCOVERY_ENABLED: "true"
  MONITORING_ENABLED: "true"
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
```

### 3. Secret Configuration

Create `k8s/secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mcp-secrets
  namespace: warehouse-mcp
type: Opaque
data:
  JWT_SECRET_KEY: <base64-encoded-secret>
  ENCRYPTION_KEY: <base64-encoded-key>
  DB_PASSWORD: <base64-encoded-password>
```

### 4. Deployment Configuration

Create `k8s/mcp-server-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
  namespace: warehouse-mcp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: warehouse-mcp:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: mcp-config
        - secretRef:
            name: mcp-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /api/v1/health/simple
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health/simple
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### 5. Service Configuration

Create `k8s/mcp-server-service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mcp-server-service
  namespace: warehouse-mcp
spec:
  selector:
    app: mcp-server
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
  type: ClusterIP
```

### 6. Ingress Configuration

Create `k8s/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mcp-ingress
  namespace: warehouse-mcp
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - mcp.warehouse.example.com
    secretName: mcp-tls
  rules:
  - host: mcp.warehouse.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: mcp-server-service
            port:
              number: 8000
```

### 7. Deploy to Kubernetes

```bash
# Apply configurations
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/mcp-server-deployment.yaml
kubectl apply -f k8s/mcp-server-service.yaml
kubectl apply -f k8s/ingress.yaml

# Check deployment status
kubectl get pods -n warehouse-mcp
kubectl get services -n warehouse-mcp
kubectl get ingress -n warehouse-mcp

# View logs
kubectl logs -f deployment/mcp-server -n warehouse-mcp
```

## Production Deployment

### 1. Infrastructure Requirements

#### High Availability Setup
- **Load Balancer**: Multiple load balancer instances
- **Database**: Primary-replica setup with failover
- **Redis**: Redis Cluster for high availability
- **Monitoring**: Redundant monitoring instances

#### Security Requirements
- **SSL/TLS**: End-to-end encryption
- **Authentication**: JWT with refresh tokens
- **Authorization**: Role-based access control
- **Network**: VPC with security groups
- **Secrets**: External secrets management

### 2. Database Setup

#### PostgreSQL with TimescaleDB
```sql
-- Create database
CREATE DATABASE warehouse;

-- Create user
CREATE USER warehouse WITH PASSWORD 'secure_password';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE warehouse TO warehouse;

-- Connect to warehouse database
\c warehouse;

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create hypertables for time-series data
SELECT create_hypertable('equipment_telemetry', 'timestamp');
SELECT create_hypertable('sensor_data', 'timestamp');
SELECT create_hypertable('audit_logs', 'timestamp');
```

#### Redis Cluster Setup
```bash
# Create Redis cluster
redis-cli --cluster create \
  192.168.1.10:7000 192.168.1.11:7000 192.168.1.12:7000 \
  192.168.1.10:7001 192.168.1.11:7001 192.168.1.12:7001 \
  --cluster-replicas 1
```

### 3. Monitoring Setup

#### Prometheus Configuration
Create `monitoring/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

scrape_configs:
  - job_name: 'mcp-server'
    static_configs:
      - targets: ['mcp-server:8000']
    metrics_path: '/api/v1/metrics'
    scrape_interval: 5s

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']
    scrape_interval: 30s

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
    scrape_interval: 30s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

#### Grafana Dashboard
Create `monitoring/grafana/dashboards/mcp-dashboard.json`:

```json
{
  "dashboard": {
    "title": "MCP System Dashboard",
    "panels": [
      {
        "title": "Tool Execution Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(mcp_tool_executions_total[5m])",
            "legendFormat": "{{tool_name}}"
          }
        ]
      },
      {
        "title": "Tool Execution Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(mcp_tool_execution_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "Error Rate",
        "type": "singlestat",
        "targets": [
          {
            "expr": "rate(mcp_tool_errors_total[5m])",
            "legendFormat": "Error Rate"
          }
        ]
      }
    ]
  }
}
```

### 4. Security Configuration

#### SSL/TLS Setup
```bash
# Generate SSL certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Configure Nginx with SSL
server {
    listen 443 ssl;
    server_name mcp.warehouse.example.com;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    location / {
        proxy_pass http://mcp-server:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### JWT Configuration
```python
# JWT settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7

# Token validation
def validate_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

## Monitoring and Logging

### 1. Metrics Collection

#### Custom Metrics
```python
from prometheus_client import Counter, Histogram, Gauge

# Tool execution metrics
tool_executions = Counter('mcp_tool_executions_total', 'Total tool executions', ['tool_name', 'status'])
tool_execution_duration = Histogram('mcp_tool_execution_duration_seconds', 'Tool execution duration', ['tool_name'])
active_connections = Gauge('mcp_active_connections', 'Active MCP connections')

# Record metrics
tool_executions.labels(tool_name='get_inventory', status='success').inc()
tool_execution_duration.labels(tool_name='get_inventory').observe(execution_time)
```

#### Health Checks
```python
@app.get("/api/v1/health")
async def health_check():
    checks = {
        "database": await check_database_health(),
        "redis": await check_redis_health(),
        "mcp_server": await check_mcp_server_health()
    }
    
    overall_health = all(checks.values())
    return {
        "status": "healthy" if overall_health else "unhealthy",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }
```

### 2. Logging Configuration

#### Structured Logging
```python
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
            
        return json.dumps(log_entry)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcp.log')
    ]
)

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.handlers[0].setFormatter(JSONFormatter())
```

### 3. Alerting Configuration

#### Alert Rules
Create `monitoring/rules/mcp-alerts.yml`:

```yaml
groups:
- name: mcp_alerts
  rules:
  - alert: HighErrorRate
    expr: rate(mcp_tool_errors_total[5m]) > 0.1
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "High error rate detected"
      description: "Error rate is {{ $value }} errors per second"

  - alert: HighResponseTime
    expr: histogram_quantile(0.95, rate(mcp_tool_execution_duration_seconds_bucket[5m])) > 5
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High response time detected"
      description: "95th percentile response time is {{ $value }} seconds"

  - alert: ServiceDown
    expr: up{job="mcp-server"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "MCP server is down"
      description: "MCP server has been down for more than 1 minute"
```

## Security Configuration

### 1. Network Security

#### Firewall Rules
```bash
# Allow only necessary ports
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw allow 8000/tcp # MCP Server
ufw deny 5432/tcp  # PostgreSQL (internal only)
ufw deny 6379/tcp  # Redis (internal only)

# Enable firewall
ufw enable
```

#### VPC Configuration
```yaml
# AWS VPC configuration
VPC:
  CIDR: 10.0.0.0/16
  Subnets:
    - Public: 10.0.1.0/24
    - Private: 10.0.2.0/24
  SecurityGroups:
    - Web: Allow HTTP/HTTPS from internet
    - Database: Allow PostgreSQL from web tier
    - Cache: Allow Redis from web tier
```

### 2. Authentication and Authorization

#### JWT Implementation
```python
from jose import JWTError, jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

#### Role-Based Access Control
```python
from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

def require_role(required_role: Role):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Check user role
            user_role = get_current_user_role()
            if not has_permission(user_role, required_role):
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def has_permission(user_role: Role, required_role: Role) -> bool:
    role_hierarchy = {
        Role.ADMIN: 3,
        Role.OPERATOR: 2,
        Role.VIEWER: 1
    }
    return role_hierarchy.get(user_role, 0) >= role_hierarchy.get(required_role, 0)
```

### 3. Data Encryption

#### Encryption at Rest
```python
from cryptography.fernet import Fernet
import base64

class EncryptionService:
    def __init__(self, key: str):
        self.cipher = Fernet(key.encode())
    
    def encrypt(self, data: str) -> str:
        encrypted_data = self.cipher.encrypt(data.encode())
        return base64.b64encode(encrypted_data).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        decoded_data = base64.b64decode(encrypted_data.encode())
        decrypted_data = self.cipher.decrypt(decoded_data)
        return decrypted_data.decode()
```

#### Encryption in Transit
```python
# HTTPS configuration
import ssl
from fastapi import FastAPI
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

app = FastAPI()

# Force HTTPS
app.add_middleware(HTTPSRedirectMiddleware)

# SSL context
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
ssl_context.load_cert_chain("cert.pem", "key.pem")
```

## Troubleshooting

### 1. Common Issues

#### Database Connection Issues
```bash
# Check database connectivity
psql -h localhost -p 5435 -U warehouse -d warehouse -c "SELECT 1;"

# Check database logs
docker logs postgres

# Check connection pool
SELECT * FROM pg_stat_activity WHERE datname = 'warehouse';
```

#### Redis Connection Issues
```bash
# Check Redis connectivity
redis-cli -h localhost -p 6379 ping

# Check Redis logs
docker logs redis

# Check Redis memory usage
redis-cli info memory
```

#### MCP Server Issues
```bash
# Check MCP server status
curl http://localhost:8000/api/v1/health/simple

# Check MCP server logs
docker logs mcp-server

# Check tool registration
curl http://localhost:8000/api/v1/tools
```

### 2. Performance Issues

#### Database Performance
```sql
-- Check slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;

-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

#### Memory Usage
```bash
# Check container memory usage
docker stats

# Check Python memory usage
python -c "import psutil; print(psutil.virtual_memory())"

# Check Redis memory usage
redis-cli info memory
```

### 3. Debugging Tools

#### Log Analysis
```bash
# Search for errors
grep -i "error" mcp.log | tail -20

# Search for specific tool
grep "get_inventory" mcp.log | tail -10

# Monitor real-time logs
tail -f mcp.log | grep -i "error"
```

#### Performance Profiling
```python
import cProfile
import pstats

# Profile tool execution
profiler = cProfile.Profile()
profiler.enable()

# Execute tool
result = await tool.execute(arguments)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)
```

## Performance Optimization

### 1. Database Optimization

#### Connection Pooling
```python
from sqlalchemy.pool import QueuePool

# Configure connection pool
engine = create_async_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600
)
```

#### Query Optimization
```python
# Use indexes
CREATE INDEX idx_equipment_status ON equipment_telemetry(equipment_id, timestamp);
CREATE INDEX idx_sensor_data ON sensor_data(sensor_id, timestamp);

# Use prepared statements
async def get_equipment_status(equipment_id: str):
    query = "SELECT * FROM equipment_telemetry WHERE equipment_id = $1 ORDER BY timestamp DESC LIMIT 1"
    async with conn.execute(query, equipment_id) as cursor:
        return await cursor.fetchone()
```

### 2. Caching Strategy

#### Redis Caching
```python
import redis
import json
from typing import Optional

class CacheService:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
    
    async def get(self, key: str) -> Optional[dict]:
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def set(self, key: str, value: dict, ttl: int = 3600):
        self.redis.setex(key, ttl, json.dumps(value))
    
    async def delete(self, key: str):
        self.redis.delete(key)
```

#### Application-Level Caching
```python
from functools import lru_cache
import asyncio

class ToolCache:
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size
    
    async def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            return self.cache[key]
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[key] = value
        
        # Schedule cleanup
        asyncio.create_task(self._cleanup(key, ttl))
    
    async def _cleanup(self, key: str, ttl: int):
        await asyncio.sleep(ttl)
        self.cache.pop(key, None)
```

### 3. Load Balancing

#### Nginx Load Balancing
```nginx
upstream mcp_backend {
    server mcp-server-1:8000 weight=3;
    server mcp-server-2:8000 weight=3;
    server mcp-server-3:8000 weight=2;
    server mcp-server-4:8000 weight=2;
}

server {
    listen 80;
    server_name mcp.warehouse.example.com;
    
    location / {
        proxy_pass http://mcp_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Health check
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504;
    }
}
```

#### Kubernetes Load Balancing
```yaml
apiVersion: v1
kind: Service
metadata:
  name: mcp-server-service
spec:
  selector:
    app: mcp-server
  ports:
  - port: 8000
    targetPort: 8000
  type: LoadBalancer
  sessionAffinity: ClientIP
```

## Conclusion

This deployment guide provides comprehensive instructions for deploying the MCP system in various environments. By following these guidelines, you can ensure a reliable, scalable, and secure deployment of the Model Context Protocol system.

For additional support or questions, please refer to the MCP system documentation or contact the development team.
