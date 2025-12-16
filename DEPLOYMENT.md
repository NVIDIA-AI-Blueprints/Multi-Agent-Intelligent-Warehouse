# Deployment Guide

Complete deployment guide for the Warehouse Operational Assistant.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [NVIDIA NIMs Deployment & Configuration](#nvidia-nims-deployment--configuration)
- [Deployment Options](#deployment-options)
- [Post-Deployment Setup](#post-deployment-setup)
- [Access Points](#access-points)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Local Development (Fastest Setup)

```bash
# 1. Clone repository
git clone  https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# 2. Verify Node.js version (recommended before setup)
./scripts/setup/check_node_version.sh

# 3. Setup environment
./scripts/setup/setup_environment.sh

# 4. Configure environment variables (REQUIRED before starting services)
# Create .env file for Docker Compose (recommended location)
cp .env.example deploy/compose/.env
# Or create in project root: cp .env.example .env
# Edit with your values: nano deploy/compose/.env

# 5. Start infrastructure services
./scripts/setup/dev_up.sh

# 6. Run database migrations
source env/bin/activate

# Load environment variables from .env file (REQUIRED before running migrations)
# This ensures $POSTGRES_PASSWORD is available for the psql commands below
# If .env is in deploy/compose/ (recommended):
set -a && source deploy/compose/.env && set +a
# OR if .env is in project root:
# set -a && source .env && set +a

# Docker Compose: Using Docker Compose (Recommended - no psql client needed)
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/000_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/001_equipment_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/002_document_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/004_inventory_movements_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < scripts/setup/create_model_tracking_tables.sql


# 7. Create default users
python scripts/setup/create_default_users.py

# 8. Generate demo data (optional but recommended)
python scripts/data/quick_demo_data.py

# 9. Generate historical demand data for forecasting (optional, required for Forecasting page)
python scripts/data/generate_historical_demand.py

# 10. (Optional) Install RAPIDS GPU acceleration for forecasting
# ⚡ GPU Acceleration: Enables 10-100x faster forecasting with NVIDIA GPUs
# Requirements:
#   - NVIDIA GPU with CUDA 12.x support
#   - CUDA Compute Capability 7.0+ (Volta, Turing, Ampere, Ada, Hopper)
#   - 16GB+ GPU memory recommended
#   - Python 3.9-3.11
#
# Installation:
./scripts/setup/install_rapids.sh
#
# Or manually:
# pip install --extra-index-url=https://pypi.nvidia.com cudf-cu12 cuml-cu12
#
# Verify installation:
# python -c "import cudf, cuml; print('✅ RAPIDS installed successfully')"
#
# Note: If RAPIDS is not installed, forecasting will use CPU fallback with XGBoost GPU support
#       The system automatically detects GPU availability and uses it when available

# 11. Start API server
./scripts/start_server.sh

# 12. Start frontend (in another terminal)
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

### Common Prerequisites
- Python 3.9+ (for local development)
- **Node.js 20.0.0+** (LTS recommended) and npm (for frontend)
  - **Minimum**: Node.js 18.17.0+ (required for `node:path` protocol support)
  - **Recommended**: Node.js 20.x LTS for best compatibility

### GPU Acceleration Prerequisites (Optional but Recommended)
For **10-100x faster forecasting** with NVIDIA RAPIDS cuML:
- **NVIDIA GPU** with CUDA 12.x support
- **CUDA Compute Capability 7.0+** (Volta, Turing, Ampere, Ada, Hopper architectures)
- **16GB+ GPU memory** (recommended for large datasets)
- **32GB+ system RAM** (recommended)
- **NVIDIA GPU drivers** (latest recommended)
- **CUDA Toolkit 12.0+** (if not using Docker)

**Note**: GPU acceleration is **optional**. The system works perfectly on CPU-only systems with automatic fallback.
  - **Note**: Node.js 18.0.0 - 18.16.x will fail with `Cannot find module 'node:path'` error during frontend build
- Git
- PostgreSQL client (`psql`) - Required for running database migrations
  - **Ubuntu/Debian**: `sudo apt-get install postgresql-client`
  - **macOS**: `brew install postgresql` or `brew install libpq`
  - **Windows**: Install from [PostgreSQL downloads](https://www.postgresql.org/download/windows/)
  - **Alternative**: Use Docker (see [Complete Setup Guide](#complete-setup-guide) notebook)

## Environment Configuration

### Required Environment Variables

**⚠️ Important:** For Docker Compose deployments, the `.env` file location matters!

Docker Compose looks for `.env` files in this order:
1. Same directory as the compose file (`deploy/compose/.env`)
2. Current working directory (project root `.env`)

**Recommended:** Create `.env` in the same directory as your compose file for consistency:

```bash
# Option 1: In deploy/compose/ (recommended for Docker Compose)
cp .env.example deploy/compose/.env
nano deploy/compose/.env  # or your preferred editor

# Option 2: In project root (works if running commands from project root)
cp .env.example .env
nano .env  # or your preferred editor
```

**Note:** If you use `docker-compose -f deploy/compose/docker-compose.dev.yaml`, Docker Compose will:
- First check for `deploy/compose/.env`
- Then check for `.env` in your current working directory
- Use the first one it finds

For consistency, we recommend placing `.env` in `deploy/compose/` when using Docker Compose.

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

# CORS (for frontend access)
CORS_ORIGINS=http://localhost:3001,http://localhost:3000
```

**⚠️ Security Notes:**
- **Development**: `JWT_SECRET_KEY` is optional (uses default with warnings)
- **Production**: `JWT_SECRET_KEY` is **REQUIRED** - application will fail to start if not set
- Always use strong, unique passwords in production
- Never commit `.env` files to version control

See [docs/secrets.md](docs/secrets.md) for detailed security configuration.

## NVIDIA NIMs Deployment & Configuration

The Warehouse Operational Assistant uses **NVIDIA NIMs (NVIDIA Inference Microservices)** for AI-powered capabilities including LLM inference, embeddings, document processing, and content safety. All NIMs use **OpenAI-compatible API endpoints**, allowing for flexible deployment options.

**Configuration Method:** All NIM endpoint URLs and API keys are configured via **environment variables**. The NeMo Guardrails SDK additionally uses Colang (`.co`) and YAML (`.yml`) configuration files for guardrails logic, but these files reference environment variables for endpoint URLs and API keys.

### NIMs Overview

The system uses the following NVIDIA NIMs:

| NIM Service | Model | Purpose | Environment Variable | Default Endpoint |
|-------------|-------|---------|---------------------|------------------|
| **LLM Service** | Llama 3.3 Nemotron Super 49B | Primary language model for chat, reasoning, and generation | `LLM_NIM_URL` | `https://api.brev.dev/v1` |
| **Embedding Service** | llama-3_2-nv-embedqa-1b-v2 | Semantic search embeddings for RAG | `EMBEDDING_NIM_URL` | `https://integrate.api.nvidia.com/v1` |
| **NeMo Retriever** | NeMo Retriever | Document preprocessing and structure analysis | `NEMO_RETRIEVER_URL` | `https://integrate.api.nvidia.com/v1` |
| **NeMo OCR** | NeMoRetriever-OCR-v1 | Intelligent OCR with layout understanding | `NEMO_OCR_URL` | `https://integrate.api.nvidia.com/v1` |
| **Nemotron Parse** | Nemotron Parse | Advanced document parsing and extraction | `NEMO_PARSE_URL` | `https://integrate.api.nvidia.com/v1` |
| **Small LLM** | nemotron-nano-12b-v2-vl | Structured data extraction and entity recognition | `LLAMA_NANO_VL_URL` | `https://integrate.api.nvidia.com/v1` |
| **Large LLM Judge** | Llama 3.3 Nemotron Super 49B | Quality validation and confidence scoring | `LLAMA_70B_URL` | `https://integrate.api.nvidia.com/v1` |
| **NeMo Guardrails** | NeMo Guardrails | Content safety and compliance validation | `RAIL_API_URL` | `https://integrate.api.nvidia.com/v1` |

### Deployment Options

NIMs can be deployed in three ways:

#### Option 1: Cloud Endpoints (Recommended for Quick Start)

Use NVIDIA-hosted cloud endpoints for immediate deployment without infrastructure setup.

**For the 49B LLM Model:**
- **Endpoint**: `https://api.brev.dev/v1`
- **Use Case**: Production deployments, quick setup
- **Configuration**: Set `LLM_NIM_URL=https://api.brev.dev/v1`

**For Other NIMs:**
- **Endpoint**: `https://integrate.api.nvidia.com/v1`
- **Use Case**: Production deployments, quick setup
- **Configuration**: Set respective environment variables (e.g., `EMBEDDING_NIM_URL=https://integrate.api.nvidia.com/v1`)

**Environment Variables:**
```bash
# NVIDIA API Key (required for all cloud endpoints)
NVIDIA_API_KEY=your-nvidia-api-key-here

# LLM Service (49B model - uses brev.dev)
LLM_NIM_URL=https://api.brev.dev/v1
LLM_MODEL=nvcf:nvidia/llama-3.3-nemotron-super-49b-v1:dep-36ZiLbQIG2ZzK7gIIC5yh1E6lGk

# Embedding Service (uses integrate.api.nvidia.com)
EMBEDDING_NIM_URL=https://integrate.api.nvidia.com/v1

# Document Processing NIMs (all use integrate.api.nvidia.com)
NEMO_RETRIEVER_URL=https://integrate.api.nvidia.com/v1
NEMO_OCR_URL=https://integrate.api.nvidia.com/v1
NEMO_PARSE_URL=https://integrate.api.nvidia.com/v1
LLAMA_NANO_VL_URL=https://integrate.api.nvidia.com/v1
LLAMA_70B_URL=https://integrate.api.nvidia.com/v1

# NeMo Guardrails
RAIL_API_URL=https://integrate.api.nvidia.com/v1
RAIL_API_KEY=your-nvidia-api-key-here  # Falls back to NVIDIA_API_KEY if not set
```

#### Option 2: Self-Hosted NIMs (Recommended for Production)

Deploy NIMs on your own infrastructure for data privacy, cost control, and custom requirements.

**Benefits:**
- **Data Privacy**: Keep sensitive data on-premises
- **Cost Control**: Avoid per-request cloud costs
- **Custom Requirements**: Full control over infrastructure and configuration
- **Low Latency**: Reduced network latency for on-premises deployments

**Deployment Steps:**

1. **Deploy NIMs on your infrastructure** (using NVIDIA NGC containers):
   ```bash
   # Example: Deploy LLM NIM on port 8000
   docker run --gpus all -p 8000:8000 \
     nvcr.io/nvidia/nim/llama-3.3-nemotron-super-49b:latest
   
   # Example: Deploy Embedding NIM on port 8001
   docker run --gpus all -p 8001:8001 \
     nvcr.io/nvidia/nim/llama-3_2-nv-embedqa-1b-v2:latest
   ```

2. **Configure environment variables** to point to your self-hosted endpoints:
   ```bash
   # Self-hosted LLM NIM
   LLM_NIM_URL=http://your-nim-host:8000/v1
   LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1
   
   # Self-hosted Embedding NIM
   EMBEDDING_NIM_URL=http://your-nim-host:8001/v1
   
   # Self-hosted Document Processing NIMs
   NEMO_RETRIEVER_URL=http://your-nim-host:8002/v1
   NEMO_OCR_URL=http://your-nim-host:8003/v1
   NEMO_PARSE_URL=http://your-nim-host:8004/v1
   LLAMA_NANO_VL_URL=http://your-nim-host:8005/v1
   LLAMA_70B_URL=http://your-nim-host:8006/v1
   
   # Self-hosted NeMo Guardrails
   RAIL_API_URL=http://your-nim-host:8007/v1
   
   # API Key (if your self-hosted NIMs require authentication)
   NVIDIA_API_KEY=your-api-key-here
   ```

3. **Verify connectivity**:
   ```bash
   # Test LLM endpoint
   curl -X POST http://your-nim-host:8000/v1/chat/completions \
     -H "Authorization: Bearer $NVIDIA_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"nvidia/llama-3.3-nemotron-super-49b-v1","messages":[{"role":"user","content":"test"}]}'
   
   # Test Embedding endpoint
   curl -X POST http://your-nim-host:8001/v1/embeddings \
     -H "Authorization: Bearer $NVIDIA_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"nvidia/llama-3_2-nv-embedqa-1b-v2","input":"test"}'
   ```

**Important Notes:**
- All NIMs use **OpenAI-compatible API endpoints** (`/v1/chat/completions`, `/v1/embeddings`, etc.)
- Self-hosted NIMs can be accessed via HTTP/HTTPS endpoints in the same fashion as cloud endpoints
- Ensure your self-hosted NIMs are accessible from the Warehouse Operational Assistant application
- For production, use HTTPS and proper authentication/authorization

#### Option 3: Hybrid Deployment

Mix cloud and self-hosted NIMs based on your requirements:

```bash
# Use cloud for LLM (49B model)
LLM_NIM_URL=https://api.brev.dev/v1

# Use self-hosted for embeddings (for data privacy)
EMBEDDING_NIM_URL=http://your-nim-host:8001/v1

# Use cloud for document processing
NEMO_RETRIEVER_URL=https://integrate.api.nvidia.com/v1
NEMO_OCR_URL=https://integrate.api.nvidia.com/v1
```

### Configuration Details

#### LLM Service Configuration

```bash
# Required: API endpoint (cloud or self-hosted)
LLM_NIM_URL=https://api.brev.dev/v1  # or http://your-nim-host:8000/v1

# Required: Model identifier
LLM_MODEL=nvcf:nvidia/llama-3.3-nemotron-super-49b-v1:dep-36ZiLbQIG2ZzK7gIIC5yh1E6lGk  # Cloud
# OR
LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1  # Self-hosted

# Required: API key (same key works for all NVIDIA endpoints)
NVIDIA_API_KEY=your-nvidia-api-key-here

# Optional: Generation parameters
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=2000
LLM_TOP_P=1.0
LLM_FREQUENCY_PENALTY=0.0
LLM_PRESENCE_PENALTY=0.0

# Optional: Client timeout (seconds)
LLM_CLIENT_TIMEOUT=120

# Optional: Caching
LLM_CACHE_ENABLED=true
LLM_CACHE_TTL_SECONDS=300
```

#### Embedding Service Configuration

```bash
# Required: API endpoint (cloud or self-hosted)
EMBEDDING_NIM_URL=https://integrate.api.nvidia.com/v1  # or http://your-nim-host:8001/v1

# Required: API key
NVIDIA_API_KEY=your-nvidia-api-key-here
```

#### NeMo Guardrails Configuration

```bash
# Required: API endpoint (cloud or self-hosted)
RAIL_API_URL=https://integrate.api.nvidia.com/v1  # or http://your-nim-host:8007/v1

# Required: API key (falls back to NVIDIA_API_KEY if not set)
RAIL_API_KEY=your-nvidia-api-key-here

# Optional: Guardrails implementation mode
USE_NEMO_GUARDRAILS_SDK=false  # Set to 'true' to use SDK with Colang (recommended)
GUARDRAILS_USE_API=true  # Set to 'false' to use pattern-based fallback
GUARDRAILS_TIMEOUT=10  # Timeout in seconds
```

### Getting NVIDIA API Keys

1. **Sign up** for NVIDIA API access at [NVIDIA API Portal](https://build.nvidia.com/)
2. **Generate API key** from your account dashboard
3. **Set environment variable**: `NVIDIA_API_KEY=your-api-key-here`

**Note:** The same API key works for all NVIDIA cloud endpoints (`api.brev.dev` and `integrate.api.nvidia.com`).

### Verification

After configuring NIMs, verify they are working:

```bash
# Test LLM endpoint
curl -X POST $LLM_NIM_URL/chat/completions \
  -H "Authorization: Bearer $NVIDIA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"'$LLM_MODEL'","messages":[{"role":"user","content":"Hello"}]}'

# Test Embedding endpoint
curl -X POST $EMBEDDING_NIM_URL/embeddings \
  -H "Authorization: Bearer $NVIDIA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"nvidia/llama-3_2-nv-embedqa-1b-v2","input":"test"}'

# Check application health (includes NIM connectivity)
curl http://localhost:8001/api/v1/health
```

### Troubleshooting NIMs

**Common Issues:**

1. **Authentication Errors (401/403)**:
   - Verify `NVIDIA_API_KEY` is set correctly
   - Ensure API key has access to the requested models
   - Check API key hasn't expired

2. **Connection Timeouts**:
   - Verify NIM endpoint URLs are correct
   - Check network connectivity to endpoints
   - Increase `LLM_CLIENT_TIMEOUT` if needed
   - For self-hosted NIMs, ensure they are running and accessible

3. **Model Not Found (404)**:
   - Verify `LLM_MODEL` matches the model available at your endpoint
   - For cloud endpoints, check model identifier format (e.g., `nvcf:nvidia/...`)
   - For self-hosted, use model name format (e.g., `nvidia/llama-3.3-nemotron-super-49b-v1`)

4. **Rate Limiting (429)**:
   - Reduce request frequency
   - Implement request queuing/retry logic
   - Consider self-hosting for higher throughput

**For detailed NIM deployment guides, see:**
- [NVIDIA NIM Documentation](https://docs.nvidia.com/nim/)
- [NVIDIA NGC Containers](https://catalog.ngc.nvidia.com/containers?filters=&orderBy=scoreDESC&query=nim)

## Deployment Options

### Complete Setup Guide

For a comprehensive, step-by-step setup guide with automated checks and interactive instructions, see:

📓 **[Complete Setup Guide (Jupyter Notebook)](notebooks/setup/complete_setup_guide.ipynb)**

This interactive notebook provides:
- Automated environment validation
- Step-by-step setup instructions
- Interactive API key configuration
- Database setup and migration guidance
- User creation and demo data generation
- Backend and frontend startup instructions

**To use the notebook:**
1. Open `notebooks/setup/complete_setup_guide.ipynb` in Jupyter Lab/Notebook
2. Follow the interactive cells step by step
3. The notebook will guide you through the entire setup process

## Post-Deployment Setup

### Database Migrations

After deployment, run database migrations:

```bash
# Docker (development - using timescaledb service)
docker-compose -f deploy/compose/docker-compose.dev.yaml exec timescaledb psql -U warehouse -d warehouse -f /docker-entrypoint-initdb.d/000_schema.sql

# Or from host using psql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql
```

**Required migration files:**
- `data/postgres/000_schema.sql`
- `data/postgres/001_equipment_schema.sql`
- `data/postgres/002_document_schema.sql`
- `data/postgres/004_inventory_movements_schema.sql`
- `scripts/setup/create_model_tracking_tables.sql`

### Create Default Users

```bash
# Docker (development)
docker-compose -f deploy/compose/docker-compose.dev.yaml exec chain_server python scripts/setup/create_default_users.py

# Or from host (recommended for development)
source env/bin/activate
python scripts/setup/create_default_users.py
```

**⚠️ Security Note:** Users are created securely via the setup script using environment variables. The SQL schema does not contain hardcoded password hashes.

### Verify Deployment

```bash
# Health check
curl http://localhost:8001/health

# API version
curl http://localhost:8001/api/v1/version
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
# Weekly VACUUM (development)
docker-compose -f deploy/compose/docker-compose.dev.yaml exec timescaledb psql -U warehouse -d warehouse -c "VACUUM ANALYZE;"

# Or from host
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -c "VACUUM ANALYZE;"

# Monthly REINDEX
docker-compose -f deploy/compose/docker-compose.dev.yaml exec timescaledb psql -U warehouse -d warehouse -c "REINDEX DATABASE warehouse;"
# Or from host
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -c "REINDEX DATABASE warehouse;"
```

### Backup and Recovery

**Database backup:**

```bash
# Create backup (development)
docker-compose -f deploy/compose/docker-compose.dev.yaml exec timescaledb pg_dump -U warehouse warehouse > backup_$(date +%Y%m%d).sql

# Or from host
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} pg_dump -h localhost -p 5435 -U warehouse warehouse > backup_$(date +%Y%m%d).sql

# Restore backup
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse warehouse < backup_20240101.sql
# Or from host
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse warehouse < backup_20240101.sql
```

## Troubleshooting

### Common Issues

#### Node.js Version Error: "Cannot find module 'node:path'"

**Symptom:**
```
Error: Cannot find module 'node:path'
Failed to compile.
[eslint] Cannot read config file
```

**Cause:**
- Node.js version is too old (below 18.17.0)
- The `node:path` protocol requires Node.js 18.17.0+ or 20.0.0+

**Solution:**
1. Check your Node.js version:
   ```bash
   node --version
   ```

2. If version is below 18.17.0, upgrade Node.js:
   ```bash
   # Using nvm (recommended)
   nvm install 20
   nvm use 20
   
   # Or download from https://nodejs.org/
   ```

3. Verify the version:
   ```bash
   node --version  # Should show v20.x.x or v18.17.0+
   ```

4. Clear node_modules and reinstall:
   ```bash
   cd src/ui/web
   rm -rf node_modules package-lock.json
   npm install
   ```

5. Run the version check script:
   ```bash
   ./scripts/setup/check_node_version.sh
   ```

**Prevention:**
- Always check Node.js version before starting: `./scripts/setup/check_node_version.sh`
- Use `.nvmrc` file: `cd src/ui/web && nvm use`
- Ensure CI/CD uses Node.js 20+

#### Frontend Port 3001 Not Accessible

**Symptom:**
```
Compiled successfully!
Local:            http://localhost:3001
On Your Network:  http://172.19.0.1:3001
```
But port 3001 is not accessible/opened.

**Possible Causes:**
1. Server binding to localhost only (not accessible from network)
2. Firewall blocking port 3001
3. Wrong IP address being used
4. Port conflict with another process

**Solution:**

1. **Verify port is listening:**
   ```bash
   # Check if port is listening
   netstat -tuln | grep 3001
   # or
   ss -tuln | grep 3001
   # Should show: 0.0.0.0:3001 (accessible from network)
   ```

2. **Ensure server binds to all interfaces:**
   The start script should include `HOST=0.0.0.0`:
   ```json
   "start": "PORT=3001 HOST=0.0.0.0 craco start"
   ```
   If not, update `src/ui/web/package.json` and restart the server.

3. **Check firewall rules:**
   ```bash
   # Linux (UFW)
   sudo ufw allow 3001/tcp
   sudo ufw status
   
   # Linux (firewalld)
   sudo firewall-cmd --add-port=3001/tcp --permanent
   sudo firewall-cmd --reload
   ```

4. **Verify correct URL:**
   - **Same machine**: `http://localhost:3001`
   - **Different machine**: `http://<server-ip>:3001` (use actual server IP, not 172.19.0.1)
   - **Docker**: May need port mapping in docker-compose

5. **Test connectivity:**
   ```bash
   # From server
   curl http://localhost:3001
   
   # From remote machine
   curl http://<server-ip>:3001
   ```

6. **Check for port conflicts:**
   ```bash
   lsof -i :3001
   # Kill conflicting process if needed
   kill -9 <PID>
   ```

**Note:** The IP `172.19.0.1` shown in the output is the Docker bridge network IP. If accessing from outside Docker, use the actual server IP address.

#### Port Already in Use

```bash
# Docker
docker-compose down
# Or change ports in docker-compose.yaml
```

#### Database Connection Errors

```bash
# Check database status (development)
docker-compose -f deploy/compose/docker-compose.dev.yaml ps timescaledb

# Test connection
docker-compose -f deploy/compose/docker-compose.dev.yaml exec timescaledb psql -U warehouse -d warehouse -c "SELECT 1;"
# Or from host
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -c "SELECT 1;"
```

#### Application Won't Start

```bash
# Check logs
docker-compose logs api

# Verify environment variables
docker-compose exec api env | grep -E "DB_|JWT_|POSTGRES_"
```

#### Password Not Working

1. Check `DEFAULT_ADMIN_PASSWORD` in `.env`
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
```

## GPU Acceleration with RAPIDS

### Overview

The forecasting system supports **NVIDIA RAPIDS cuML** for GPU-accelerated demand forecasting, providing **10-100x performance improvements** over CPU-only execution.

### Key Benefits

- **🚀 10-100x Faster Training**: GPU-accelerated model training with cuML
- **⚡ Real-Time Inference**: Sub-second predictions for large datasets
- **🔄 Automatic Fallback**: Seamlessly falls back to CPU if GPU unavailable
- **📊 Full Model Support**: Random Forest, Linear Regression, SVR via cuML; XGBoost via CUDA
- **🎯 Zero Code Changes**: Works automatically when RAPIDS is installed

### Installation

#### Quick Install (Recommended)

```bash
# Activate virtual environment
source env/bin/activate

# Run installation script
./scripts/setup/install_rapids.sh
```

#### Manual Installation

```bash
# Activate virtual environment
source env/bin/activate

# Install RAPIDS cuDF and cuML
pip install --extra-index-url=https://pypi.nvidia.com cudf-cu12 cuml-cu12
```

#### Verify Installation

```bash
python -c "import cudf, cuml; print('✅ RAPIDS installed successfully')"
```

### Usage

Once installed, RAPIDS is **automatically detected and used** when:
1. GPU is available and CUDA is properly configured
2. Training is initiated from the Forecasting page
3. The system will show: `🚀 GPU acceleration: ✅ Enabled (RAPIDS cuML)`

### Performance Metrics

With RAPIDS enabled, you can expect:
- **Training Time**: 10-100x faster than CPU-only
- **Inference Speed**: Sub-second predictions for 38+ SKUs
- **Memory Efficiency**: Optimized GPU memory usage
- **Scalability**: Linear scaling with additional GPUs

### Troubleshooting

**GPU not detected?**
- Verify NVIDIA drivers: `nvidia-smi`
- Check CUDA version: `nvcc --version` (should be 12.0+)
- Ensure GPU has compute capability 7.0+

**RAPIDS installation failed?**
- Check Python version (3.9-3.11 supported)
- Verify CUDA toolkit is installed
- Try manual installation: `pip install --extra-index-url=https://pypi.nvidia.com cudf-cu12 cuml-cu12`

**System falls back to CPU?**
- This is normal if GPU is unavailable
- CPU fallback still works with XGBoost GPU support
- Check logs for: `⚠️ RAPIDS cuML not available - checking for XGBoost GPU support...`

### Additional Resources

- **Detailed RAPIDS Setup**: [docs/forecasting/RAPIDS_SETUP.md](docs/forecasting/RAPIDS_SETUP.md)
- **RAPIDS Documentation**: https://rapids.ai/
- **NVIDIA cuML**: https://docs.rapids.ai/api/cuml/stable/

## Additional Resources

- **Security Guide**: [docs/secrets.md](docs/secrets.md)
- **API Documentation**: http://localhost:8001/docs (when running)
- **Architecture**: [README.md](README.md)
- **RAPIDS Setup Guide**: [docs/forecasting/RAPIDS_SETUP.md](docs/forecasting/RAPIDS_SETUP.md)

## Support

- **Issues**: [GitHub Issues](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues)
- **Documentation**: [docs/](docs/)
- **Main README**: [README.md](README.md)
