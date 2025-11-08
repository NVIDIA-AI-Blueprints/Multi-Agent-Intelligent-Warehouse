# Development Secrets & Credentials

## Default Development Credentials

** WARNING: These are development-only credentials. NEVER use in production!**

### Authentication
- **Username**: `admin`
- **Password**: `password123`
- **Role**: `admin`

### Database
- **Host**: `localhost`
- **Port**: `5435`
- **Database**: `warehouse_assistant`
- **Username**: `postgres`
- **Password**: `postgres`

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

## JWT Secret Example

**Sample JWT secret (change in production):**
```
your-super-secret-jwt-key-here-must-be-at-least-32-characters-long
```

** This is a sample only - change in production!**
