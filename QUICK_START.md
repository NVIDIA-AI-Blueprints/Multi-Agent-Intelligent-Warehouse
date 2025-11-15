# Quick Start Guide

## 🚀 Fastest Way to Get Started

### 1. Setup (One-time)

```bash
# Setup virtual environment and install dependencies
./scripts/setup/setup_environment.sh
```

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

## 🔧 Troubleshooting

**Server won't start?**
```bash
# Make sure virtual environment is set up
./scripts/setup/setup_environment.sh

# Then start server
./scripts/start_server.sh
```

**Password not working?**
- Default password is `changeme`
- Check your `.env` file for `DEFAULT_ADMIN_PASSWORD`
- Recreate users: `python scripts/setup/create_default_users.py`

**Port already in use?**
```bash
# Use a different port
PORT=8002 ./scripts/start_server.sh
```

## 📚 More Information

- Full deployment guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- All credentials: [docs/secrets.md](docs/secrets.md)
- Main README: [README.md](README.md)

