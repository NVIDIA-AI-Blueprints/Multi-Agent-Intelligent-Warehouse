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
2. **Use secrets management systems in production**
3. **Rotate credentials regularly**
4. **Use least privilege principle**
5. **Enable audit logging**
6. **Use secure communication protocols**
7. **Implement proper access controls**
8. **Regular security audits**

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
