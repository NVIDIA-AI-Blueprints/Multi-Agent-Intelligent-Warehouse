# Quick Start Guide

**For complete deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)**

## Fastest Way to Get Started

### Prerequisites

- Python 3.9+
- Docker and Docker Compose
- Node.js 18+ and npm (for frontend)

### Quick Setup

```bash
# 1. Clone repository
git clone https://github.com/T-DevH/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# 2. Setup environment
./scripts/setup/setup_environment.sh

# 3. Start database services
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

### Access the Application

- **Frontend UI:** http://localhost:3001
- **API Server:** http://localhost:8001
- **API Docs:** http://localhost:8001/docs

### Default Login

- **Username:** `admin`
- **Password:** `changeme`

⚠️ **Change default passwords before production use!**

## Next Steps

- **Full Deployment Guide**: [DEPLOYMENT.md](DEPLOYMENT.md) - Complete instructions for Docker and Kubernetes deployments
- **Security Configuration**: [docs/secrets.md](docs/secrets.md)
- **Troubleshooting**: See [DEPLOYMENT.md](DEPLOYMENT.md#troubleshooting)
