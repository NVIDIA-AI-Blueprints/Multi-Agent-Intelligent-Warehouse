# Development Secrets & Credentials

## Default Development Credentials

** WARNING: These are development-only credentials. NEVER use in production!**

### Authentication
- **Username**: `admin`
- **Password**: Set via `DEFAULT_ADMIN_PASSWORD` environment variable (default: `changeme`)
- **Role**: `admin`

### Database
- **Host**: `localhost`
- **Port**: `5435`
- **Database**: Set via `POSTGRES_DB` environment variable (default: `warehouse`)
- **Username**: Set via `POSTGRES_USER` environment variable (default: `warehouse`)
- **Password**: Set via `POSTGRES_PASSWORD` environment variable (default: `changeme`)

### Redis
- **Host**: `localhost`
- **Port**: `6379`
- **Password**: None (development only)

### Milvus
- **Host**: `localhost`
- **Port**: `19530`
- **Username**: None
- **Password**: None

## Production Security

### Required Changes for Production

1. **Change all default passwords**
2. **Use strong, unique passwords**
3. **Enable database authentication**
4. **Use environment variables for all secrets**
5. **Enable HTTPS/TLS**
6. **Use proper JWT secrets**
7. **Enable Redis authentication**
8. **Use secure database connections**

### Environment Variables

Create a `.env` file with production values:

```bash
# Database
DATABASE_URL=postgresql://username:password@host:port/database
REDIS_URL=redis://username:password@host:port

# JWT
JWT_SECRET_KEY=your-super-secret-jwt-key-here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# NVIDIA NIMs
NIM_LLM_URL=your-nim-llm-url
NIM_EMBEDDINGS_URL=your-nim-embeddings-url
NIM_API_KEY=your-nim-api-key

# External Services
WMS_API_KEY=your-wms-api-key
ERP_API_KEY=your-erp-api-key
```

## Security Best Practices

1. **Never commit secrets to version control**
2. **Never hardcode password hashes in SQL files or source code**
   - Password hashes should be generated dynamically from environment variables
   - Use the setup script (`scripts/setup/create_default_users.py`) to create users securely
   - The SQL schema (`data/postgres/000_schema.sql`) does not contain hardcoded credentials
3. **Use secrets management systems in production**
4. **Rotate credentials regularly**
5. **Use least privilege principle**
6. **Enable audit logging**
7. **Use secure communication protocols**
8. **Implement proper access controls**
9. **Regular security audits**

## User Creation Security

### ⚠️ Important: Never Hardcode Password Hashes

**The SQL schema file (`data/postgres/000_schema.sql`) does NOT contain hardcoded password hashes or sample user data.** This is a security best practice to prevent credential exposure in source code.

### Creating Users Securely

Users must be created using the setup script, which:
- Generates unique bcrypt hashes with random salts
- Reads passwords from environment variables (never hardcoded)
- Does not expose credentials in source code

**To create default users:**
```bash
# Set password via environment variable
export DEFAULT_ADMIN_PASSWORD=your-secure-password-here

# Run the setup script
python scripts/setup/create_default_users.py
```

**Environment Variables:**
- `DEFAULT_ADMIN_PASSWORD` - Password for the admin user (default: `changeme` for development only)
- `DEFAULT_USER_PASSWORD` - Password for regular users (default: `changeme` for development only)

**For Production:**
- Always set strong, unique passwords via environment variables
- Never use default passwords in production
- Consider using a secrets management system (AWS Secrets Manager, HashiCorp Vault, etc.)

## JWT Secret Configuration

### Development vs Production Behavior

**Development Mode (default):**
- If `JWT_SECRET_KEY` is not set or uses the placeholder value, the application will:
  - Use a default development key
  - Log warnings about using the default key
  - Continue to run normally
- This allows for easy local development without requiring secret configuration

**Production Mode:**
- Set `ENVIRONMENT=production` in your `.env` file
- The application **requires** `JWT_SECRET_KEY` to be set with a secure value
- If `JWT_SECRET_KEY` is not set or uses the placeholder, the application will:
  - Log an error
  - Exit immediately (fail to start)
  - Prevent deployment with insecure defaults

### Setting JWT_SECRET_KEY

**For Development:**
```bash
# Optional - application will use default if not set
JWT_SECRET_KEY=dev-secret-key-change-in-production-not-for-production-use
```

**For Production (REQUIRED):**
```bash
# Generate a strong random secret (minimum 32 characters)
JWT_SECRET_KEY=your-super-secret-jwt-key-here-must-be-at-least-32-characters-long
ENVIRONMENT=production
```

**Generating a Secure Secret:**
```bash
# Using OpenSSL
openssl rand -hex 32

# Using Python
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### JWT Secret Example

**Sample JWT secret (change in production):**
```
your-super-secret-jwt-key-here-must-be-at-least-32-characters-long
```

**⚠️ This is a sample only - change in production!**

**Security Note:** The JWT secret key is critical for security. Never commit it to version control, use a secrets management system in production, and rotate it regularly.
