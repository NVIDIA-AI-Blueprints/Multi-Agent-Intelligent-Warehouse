# Login Troubleshooting Guide

**Issue:** Login failing with "Invalid username or password" at http://localhost:3000/login

## Problem Identified

### Port Confusion
- **Port 3000:** Running Grafana (monitoring tool), NOT the React app
- **Port 3001:** Correct port for the React frontend application
- **You are accessing the wrong port!**

## Solution

### ✅ Correct Login URL
**Use:** http://localhost:3001/login (NOT port 3000)

### ✅ Correct Credentials
- **Username:** `admin`
- **Password:** `changeme`

## Verification Steps

### 1. Verify Backend is Running
```bash
curl http://localhost:8001/api/v1/health
```

Should return: `{"ok":true,"status":"healthy"}`

### 2. Test Login Endpoint Directly
```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'
```

Should return JWT tokens if successful.

### 3. Reset Admin Password (if needed)
If the password still doesn't work, reset it:

```bash
# Activate virtual environment
source env/bin/activate

# Run user creation script (updates password)
python scripts/setup/create_default_users.py
```

This will:
- Update the admin password to match `DEFAULT_ADMIN_PASSWORD` env var (default: "changeme")
- Print the current password to console

### 4. Check Environment Variables
```bash
# Check what password is configured
grep DEFAULT_ADMIN_PASSWORD .env

# If not set, default is "changeme"
```

## Common Issues

### Issue 1: Wrong Port
**Symptom:** Accessing http://localhost:3000/login
**Solution:** Use http://localhost:3001/login instead

### Issue 2: Wrong Password
**Symptom:** "Invalid username or password" error
**Solution:** 
- Default password is `changeme`
- Check `.env` file for `DEFAULT_ADMIN_PASSWORD`
- Run `python scripts/setup/create_default_users.py` to reset

### Issue 3: Password Not Updated in Database
**Symptom:** Password changed in `.env` but login still fails
**Solution:** Run `python scripts/setup/create_default_users.py` to update database

### Issue 4: Frontend Not Running
**Symptom:** Cannot access http://localhost:3001/login
**Solution:**
```bash
cd src/ui/web
npm start
```

## Quick Fix Commands

```bash
# 1. Reset admin password
source env/bin/activate
python scripts/setup/create_default_users.py

# 2. Verify backend is running
curl http://localhost:8001/api/v1/health

# 3. Test login
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'

# 4. Access correct frontend URL
# Open browser: http://localhost:3001/login
```

## Summary

**Correct Login Information:**
- **URL:** http://localhost:3001/login (NOT 3000)
- **Username:** admin
- **Password:** changeme

**If login still fails:**
1. Verify you're using port 3001 (not 3000)
2. Verify password is "changeme"
3. Run `python scripts/setup/create_default_users.py` to reset password
4. Check backend is running on port 8001

