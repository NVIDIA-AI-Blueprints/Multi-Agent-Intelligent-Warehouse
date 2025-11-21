# Deployment Guide

## Quick Start

### 1. Setup Environment

```bash
# Make scripts executable
chmod +x scripts/setup/*.sh scripts/*.sh

# Setup virtual environment and install dependencies
./scripts/setup/setup_environment.sh
```

### 2. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file with your configuration
nano .env  # or use your preferred editor
```

**Required environment variables:**
- `POSTGRES_PASSWORD` - Database password (default: `changeme`)
- `DEFAULT_ADMIN_PASSWORD` - Admin user password (default: `changeme`)
- `JWT_SECRET_KEY` - JWT secret for authentication
  - **Development**: Optional - application uses a default with warnings if not set
  - **Production**: **REQUIRED** - Application will fail to start if not set. Set `ENVIRONMENT=production` and provide a strong, unique secret (minimum 32 characters)
  - See [docs/secrets.md](docs/secrets.md) for security best practices
- `NIM_API_KEY` - NVIDIA API key (if using NVIDIA NIMs)

### 3. Start Database Services

```bash
# Using the setup script (recommended)
./scripts/setup/dev_up.sh

# Or manually using Docker Compose
docker-compose -f deploy/compose/docker-compose.dev.yaml up -d postgres redis milvus
```

**Service Endpoints:**
- **Postgres/Timescale**: `localhost:5435`
- **Redis**: `localhost:6379`
- **Milvus**: `localhost:19530`
- **Kafka**: `localhost:9092`

### 4. Run Database Migrations

```bash
# Activate virtual environment
source env/bin/activate

# Run migrations
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/001_equipment_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/002_document_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/004_inventory_movements_schema.sql

# Create model tracking tables (required for forecasting features)
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f scripts/setup/create_model_tracking_tables.sql
```

### 5. Create Default Users

```bash
# Activate virtual environment
source env/bin/activate

# Create default admin and user accounts
python scripts/setup/create_default_users.py
```

**Default Login Credentials:**
- **Username:** `admin`
- **Password:** `changeme` (or value of `DEFAULT_ADMIN_PASSWORD` env var)

### 6. (Optional) Install RAPIDS for GPU-Accelerated Forecasting

For GPU-accelerated demand forecasting (10-100x faster), install NVIDIA RAPIDS:

```bash
# Activate virtual environment
source env/bin/activate

# Install RAPIDS cuML (requires NVIDIA GPU with CUDA 11.2+ or 12.0+)
./scripts/setup/install_rapids.sh
```

**Requirements:**
- NVIDIA GPU with CUDA Compute Capability 7.0+
- CUDA 11.2+ or 12.0+
- 16GB+ GPU memory (recommended)

The system will automatically use GPU acceleration when RAPIDS is available, with CPU fallback otherwise.

See [RAPIDS Setup Guide](docs/forecasting/RAPIDS_SETUP.md) for detailed instructions.

### 7. Start API Server

```bash
# Start the server (automatically activates virtual environment)
./scripts/start_server.sh

# Or manually:
source env/bin/activate
python -m uvicorn src.api.app:app --reload --port 8001 --host 0.0.0.0
```

**Verify Server is Running:**
```bash
# Check health endpoint
curl http://localhost:8001/health

# Check version endpoint
curl http://localhost:8001/api/v1/version
```

### 8. Start Frontend (Optional)

```bash
cd src/ui/web
npm install
npm start
```

The frontend will be available at http://localhost:3001

## Access Points

Once everything is running:

- **Frontend UI:** http://localhost:3001
  - **Login:** `admin` / `changeme` (or your `DEFAULT_ADMIN_PASSWORD`)
- **API Server:** http://localhost:8001
- **API Documentation:** http://localhost:8001/docs
- **Health Check:** http://localhost:8001/health

## Default Credentials

### UI Login
- **Username:** `admin`
- **Password:** `changeme` (default, set via `DEFAULT_ADMIN_PASSWORD` env var)

### Database
- **Host:** `localhost`
- **Port:** `5435`
- **Database:** `warehouse`
- **Username:** `warehouse`
- **Password:** `changeme` (default, set via `POSTGRES_PASSWORD` env var)

### Grafana (if monitoring is enabled)
- **Username:** `admin`
- **Password:** `changeme` (default, set via `GRAFANA_ADMIN_PASSWORD` env var)

## Troubleshooting

### Virtual Environment Not Found
```bash
./scripts/setup/setup_environment.sh
```

### Port Already in Use
```bash
# Kill process on port 8001
lsof -ti:8001 | xargs kill -9

# Or use a different port
PORT=8002 ./scripts/start_server.sh
```

### Module Not Found Errors

If you see errors like `ModuleNotFoundError: No module named 'fastapi'` or similar:

```bash
# Activate virtual environment
source env/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Common missing dependencies that may need explicit installation:
pip install tiktoken redis python-multipart scikit-learn pandas xgboost
```

**Note:** All required dependencies are listed in `requirements.txt`. If you encounter missing modules, ensure the virtual environment is activated and dependencies are installed.

### Database Connection Errors
1. Check if PostgreSQL is running: `docker ps | grep postgres`
2. Verify connection string in `.env` file
3. Check database credentials

### Password Not Working
1. Check `DEFAULT_ADMIN_PASSWORD` in `.env` file
2. Recreate users: `python scripts/setup/create_default_users.py`
3. Default password is `changeme` if not set

### Server Won't Start

**Check virtual environment:**
```bash
# Ensure virtual environment exists and is activated
./scripts/setup/setup_environment.sh
source env/bin/activate
```

**Check port availability:**
```bash
# Check if port 8001 is in use
lsof -i :8001

# Use a different port if needed
PORT=8002 ./scripts/start_server.sh
```

**Check dependencies:**
```bash
# Verify all dependencies are installed
source env/bin/activate
pip list | grep -E "fastapi|uvicorn|pydantic"
```

**View server logs:**
```bash
# If running manually, check terminal output
# If using startup script, check for error messages
```

## Production Deployment

For comprehensive production deployment instructions, see:
- [Comprehensive Deployment Guide](docs/deployment/README.md) - Docker, Kubernetes, monitoring, security, scaling, backup
- [Security Best Practices](docs/secrets.md)

**Important:** Change all default passwords before deploying to production!

