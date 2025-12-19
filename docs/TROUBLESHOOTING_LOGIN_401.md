# Troubleshooting 401 Login Error

## Quick Checklist

If you're getting a **401 Unauthorized** error when trying to log in to the UI, follow these steps:

### 1. Verify Backend is Running

**Check if backend is accessible:**
```bash
# Health check
curl http://localhost:8001/health

# Should return: {"status":"healthy"}
```

**If backend is not running:**
- Check Step 11 in the notebook - ensure backend was started successfully
- Look for any error messages in the backend terminal/logs
- Verify the backend process is running: `ps aux | grep uvicorn`

### 2. Verify Default User Exists

The default admin user must be created in the database. This happens automatically when:
- Running `scripts/setup/create_default_users.py`
- Or when the backend starts for the first time (if configured)

**Check if user exists:**
```bash
# Connect to database
PGPASSWORD=changeme psql -h localhost -p 5435 -U warehouse -d warehouse

# Check users table
SELECT username, email, role, status FROM users;

# Should show:
# username | email              | role  | status
# ---------+--------------------+-------+--------
# admin    | admin@warehouse.com| admin | active
```

**If user doesn't exist, create it:**
```bash
# From project root
source env/bin/activate
python scripts/setup/create_default_users.py
```

### 3. Verify Default Password

**Default credentials:**
- **Username**: `admin`
- **Password**: Check your `.env` file for `DEFAULT_ADMIN_PASSWORD`
  - Default value: `changeme` (if not set)
  - **Important**: The password in `.env` must match what was used to create the user

**Check your .env file:**
```bash
grep DEFAULT_ADMIN_PASSWORD .env
```

**If password doesn't match:**
1. Update `.env` with the correct password
2. Re-run user creation script to update the password hash:
   ```bash
   source env/bin/activate
   python scripts/setup/create_default_users.py
   ```
3. Restart the backend

### 4. Check JWT Configuration

**Verify JWT_SECRET_KEY is set:**
```bash
grep JWT_SECRET_KEY .env
```

**If not set or using placeholder:**
- In development, the app will generate a random key, but it changes on restart
- **Solution**: Set a fixed `JWT_SECRET_KEY` in `.env`:
  ```bash
  # Generate a secure key
  openssl rand -hex 32
  
  # Add to .env
  JWT_SECRET_KEY=your-generated-key-here
  ```
- Restart backend after setting

### 5. Check Backend Logs

**Look for authentication errors in backend logs:**
```bash
# If backend is running in terminal, check for:
# - "User not found" messages
# - "Authentication failed" messages
# - Database connection errors
# - "User service initialization failed" messages
```

**Common log messages:**
- ✅ `User admin logged in successfully` - Login worked
- ❌ `User not found: admin` - User doesn't exist in database
- ❌ `Authentication failed for user: admin` - Wrong password
- ❌ `User service initialization failed` - Database connection issue

### 6. Verify Database Connection

**Check if backend can connect to database:**
```bash
# Test database connection
PGPASSWORD=changeme psql -h localhost -p 5435 -U warehouse -d warehouse -c "SELECT 1;"
```

**If connection fails:**
- Verify TimescaleDB is running (Step 6 in notebook)
- Check `.env` has correct database credentials:
  ```bash
  grep -E "POSTGRES_|DB_" .env
  ```
- Ensure port 5435 is correct (not 5432)

### 7. Check Frontend-Backend Connection

**Verify frontend can reach backend:**
```bash
# From browser console (F12), check Network tab:
# - Look for POST request to /api/v1/auth/login
# - Check if request reaches backend (status 401 vs network error)
# - Check response body for error details
```

**If frontend can't reach backend:**
- Verify backend is on port 8001
- Check if proxy is configured correctly (for development)
- Check browser console for CORS errors

### 8. Clear Browser Cache and Local Storage

**Sometimes cached tokens cause issues:**
1. Open browser DevTools (F12)
2. Go to Application tab → Local Storage
3. Clear `auth_token` and `user_info`
4. Refresh page and try login again

### 9. Test Login via API Directly

**Bypass frontend to test backend:**
```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'
```

**Expected response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

**If this works but UI doesn't:**
- Frontend configuration issue
- Check browser console for errors
- Verify API base URL in frontend

**If this fails:**
- Backend authentication issue
- Check backend logs
- Verify user exists and password is correct

## Step-by-Step Recovery

If login still fails, follow this complete recovery:

### Step 1: Stop Everything
```bash
# Stop backend (Ctrl+C in terminal where it's running)
# Stop frontend (Ctrl+C in terminal where it's running)
```

### Step 2: Verify Environment
```bash
# Check .env file exists and has required variables
cat .env | grep -E "DEFAULT_ADMIN_PASSWORD|JWT_SECRET_KEY|POSTGRES_|DB_"
```

### Step 3: Recreate Default User
```bash
source env/bin/activate
python scripts/setup/create_default_users.py
```

**Expected output:**
```
✅ Default admin user created
Login credentials:
   Username: admin
   Password: [REDACTED - check environment variable DEFAULT_ADMIN_PASSWORD]
```

### Step 4: Restart Backend
```bash
# From project root
source env/bin/activate
cd src/api
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

**Watch for:**
- ✅ `Application startup complete`
- ✅ No database connection errors
- ✅ User service initialized successfully

### Step 5: Test Login via API
```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'
```

### Step 6: Restart Frontend
```bash
cd src/ui/web
npm start
```

### Step 7: Try Login in UI
- Username: `admin`
- Password: Value from `DEFAULT_ADMIN_PASSWORD` in `.env` (default: `changeme`)

## Common Issues and Solutions

### Issue: "User not found"
**Cause**: User not created in database  
**Solution**: Run `python scripts/setup/create_default_users.py`

### Issue: "Invalid username or password"
**Cause**: Password hash doesn't match  
**Solution**: 
1. Check `DEFAULT_ADMIN_PASSWORD` in `.env`
2. Re-run user creation script
3. Restart backend

### Issue: "Authentication service is unavailable"
**Cause**: Database connection timeout  
**Solution**:
1. Verify TimescaleDB is running
2. Check database credentials in `.env`
3. Test database connection manually

### Issue: Network error (not 401)
**Cause**: Backend not running or not accessible  
**Solution**:
1. Verify backend is running on port 8001
2. Check firewall/port blocking
3. Verify frontend proxy configuration

### Issue: CORS errors
**Cause**: Frontend and backend on different origins  
**Solution**:
1. Ensure using proxy in development (frontend should use `/api/v1`)
2. Check `CORS_ORIGINS` in backend `.env`
3. Verify backend allows frontend origin

## Still Having Issues?

If none of the above works, please provide:

1. **Backend logs** (from terminal where backend is running)
2. **Browser console errors** (F12 → Console tab)
3. **Network request details** (F12 → Network tab → find login request)
4. **Output of**:
   ```bash
   curl http://localhost:8001/health
   curl http://localhost:8001/api/v1/version
   ```
5. **Contents of** `.env` (redact sensitive values):
   ```bash
   grep -E "DEFAULT_ADMIN_PASSWORD|JWT_SECRET_KEY|POSTGRES_|DB_" .env
   ```

## Quick Reference

**Default Credentials:**
- Username: `admin`
- Password: `changeme` (or value from `DEFAULT_ADMIN_PASSWORD` in `.env`)

**Key Endpoints:**
- Health: `http://localhost:8001/health`
- Login API: `http://localhost:8001/api/v1/auth/login`
- Frontend: `http://localhost:3001`

**Key Files:**
- `.env` - Environment variables (passwords, keys)
- `scripts/setup/create_default_users.py` - User creation script
- Backend logs - Authentication errors and issues

