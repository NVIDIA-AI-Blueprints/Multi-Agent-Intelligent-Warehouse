# Quick Start Guide

## 🚀 Fastest Way to Get Started

### Prerequisites

- Python 3.9+ installed
- Docker and Docker Compose installed
- Node.js 18+ and npm (for frontend)

### 1. Setup (One-time)

```bash
# Setup virtual environment and install dependencies
./scripts/setup/setup_environment.sh

# Start database services
./scripts/setup/dev_up.sh

# Run database migrations
source env/bin/activate
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/001_equipment_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/002_document_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/004_inventory_movements_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f scripts/setup/create_model_tracking_tables.sql

# Create default users (generates secure password hashes from environment variables)
python scripts/setup/create_default_users.py
```

**⚠️ Security Note:** The SQL schema does not contain hardcoded password hashes. Users are created securely via the setup script using environment variables.

**Note:** For detailed setup instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)

### 2. Start Server

```bash
# Start the API server
./scripts/start_server.sh
```

### 3. Access the Application

**Frontend UI:** http://localhost:3001

**Login Credentials:**
- **Username:** `admin`
- **Password:** `changeme`

**API Server:** http://localhost:8001  
**API Docs:** http://localhost:8001/docs

## 📝 Default Credentials

### UI Login
- **Username:** `admin`
- **Password:** `changeme`

### Database
- **Host:** `localhost:5435`
- **Database:** `warehouse`
- **Username:** `warehouse`
- **Password:** `changeme`

### Security Configuration

**JWT Secret Key:**
- **Development**: Not required - application uses a default with warnings
- **Production**: **REQUIRED** - Set `JWT_SECRET_KEY` in `.env` file. Application will fail to start if not set.
- See [docs/secrets.md](docs/secrets.md) for details on JWT configuration and security best practices.

## 🔧 Troubleshooting

**Server won't start?**
```bash
# Make sure virtual environment is set up
./scripts/setup/setup_environment.sh

# Then start server
./scripts/start_server.sh
```

**Password not working?**
- Default password is `changeme` (development only)
- Check your `.env` file for `DEFAULT_ADMIN_PASSWORD` environment variable
- Recreate users: `python scripts/setup/create_default_users.py`
- **Note:** The SQL schema does not create users - they must be created via the setup script

**Port already in use?**
```bash
# Use a different port
PORT=8002 ./scripts/start_server.sh
```

## 📚 More Information

- Full deployment guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- All credentials: [docs/secrets.md](docs/secrets.md)
- Main README: [README.md](README.md)

