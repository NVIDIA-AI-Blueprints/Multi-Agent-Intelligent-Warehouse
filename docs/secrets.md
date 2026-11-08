# Development Secrets & Credentials

## Default Development Credentials

** WARNING: These are development-only credentials. NEVER use in production!**

### No user login
The blueprint has no user accounts, passwords or sessions. The `users` table is
the worker roster. Governed writes are gated by `MAIW_OPERATOR_WRITE_TOKEN`, and
`POST /api/v1/inference` by `MAIW_INFERENCE_INTERNAL_TOKEN` (see below).

### Database
- **Host**: `localhost`
- **Port**: `5435`
- **Database**: Set via `POSTGRES_DB` environment variable (default: `warehouse`)
- **Username**: Set via `POSTGRES_USER` environment variable (default: `warehouse`)
- **Password**: Set via `POSTGRES_PASSWORD` environment variable (required; `.env.example` ships the placeholder `changeme`)

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
6. **Enable Redis authentication**
7. **Use secure database connections**

### Environment Variables

Create a `.env` file with production values:

```bash
# Database
DATABASE_URL=postgresql://username:password@host:port/database
POSTGRES_PASSWORD=your-db-password
REDIS_PASSWORD=your-redis-password

# NVIDIA NIMs
NVIDIA_API_KEY=your-nvidia-api-key
LLM_NIM_URL=https://integrate.api.nvidia.com/v1
EMBEDDING_NIM_URL=https://integrate.api.nvidia.com/v1

# MAIW API credentials (each >= 32 chars; must differ from each other)
MAIW_INFERENCE_INTERNAL_TOKEN=your-inference-token   # the only credential given to the sandbox
MAIW_OPERATOR_WRITE_TOKEN=your-operator-write-token  # reference_governed only; never given to the sandbox
```

See the "Secrets" table in [operations/REFERENCE_DEPLOYMENT_RUNBOOK.md](operations/REFERENCE_DEPLOYMENT_RUNBOOK.md) for who holds each secret and what to restart on rotation.

## Security Best Practices

1. **Never commit secrets to version control**
2. **Never hardcode credentials in SQL files or source code**
3. **Use secrets management systems in production**
4. **Rotate credentials regularly**
5. **Use least privilege principle**
6. **Enable audit logging**
7. **Use secure communication protocols**
8. **Implement proper access controls**
9. **Regular security audits**
