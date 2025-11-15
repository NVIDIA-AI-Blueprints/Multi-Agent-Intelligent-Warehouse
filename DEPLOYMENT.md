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
- `NIM_API_KEY` - NVIDIA API key (if using NVIDIA NIMs)

### 3. Start Database Services

```bash
# Using Docker Compose
docker-compose -f deploy/compose/docker-compose.dev.yaml up -d postgres redis milvus
```

### 4. Run Database Migrations

```bash
# Activate virtual environment
source env/bin/activate

# Run migrations
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/001_equipment_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/002_document_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/004_inventory_movements_schema.sql
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

### 6. Start API Server

```bash
# Start the server (automatically activates virtual environment)
./scripts/start_server.sh

# Or manually:
source env/bin/activate
python -m uvicorn src.api.app:app --reload --port 8001 --host 0.0.0.0
```

### 7. Start Frontend (Optional)

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
```bash
source env/bin/activate
pip install -r requirements.txt
```

### Database Connection Errors
1. Check if PostgreSQL is running: `docker ps | grep postgres`
2. Verify connection string in `.env` file
3. Check database credentials

### Password Not Working
1. Check `DEFAULT_ADMIN_PASSWORD` in `.env` file
2. Recreate users: `python scripts/setup/create_default_users.py`
3. Default password is `changeme` if not set

## Production Deployment

For production deployment, see:
- [Production Deployment Guide](docs/deployment/README.md)
- [Security Best Practices](docs/secrets.md)

**Important:** Change all default passwords before deploying to production!

